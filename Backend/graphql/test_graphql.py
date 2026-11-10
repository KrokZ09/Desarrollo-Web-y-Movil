import copy
import os

import httpx

# Se configura el entorno ANTES de importar la app
os.environ["GW_GRAPHQL"] = "tok-gw-graphql"
os.environ["GRAPHQL_ORDERS"] = "tok-graphql-orders"
os.environ["GRAPHQL_INVENTORY"] = "tok-graphql-inventory"

from fastapi.testclient import TestClient  # noqa: E402

import limits  # noqa: E402
import main  # noqa: E402
import resolvers  # noqa: E402

client = TestClient(main.app)

ORDER = {
    "id": 15,
    "estado": "PENDIENTE_PAGO",
    "total": 16300,
    "creadoEn": "2026-11-09T12:00:00+00:00",
    "direccionEntrega": "Calle Falsa 123, Paine",
    "items": [
        {"productId": 1, "nombre": "Ravioles", "precioUnitario": 5900, "cantidad": 2},
        {"productId": 2, "nombre": "Fettuccine", "precioUnitario": 4500, "cantidad": 1},
    ],
}
PRODUCTS = [
    {"id": 1, "nombre": "Ravioles", "descripcion": "Pasta fresca rellena.", "precio": 5900, "disponible": True},
    {"id": 2, "nombre": "Fettuccine", "descripcion": "Fettuccine fresco.", "precio": 4500, "disponible": True},
]
CALLS = []
STATE = {"orders": 200, "orders_error": None, "inventory_down": False}


class Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return copy.deepcopy(self._data)


async def fake_http_get(url, headers):
    """Simula orders e inventory: sin red."""
    CALLS.append((url, headers))
    if "/orders/" in url:
        if STATE["orders_error"]:
            raise STATE["orders_error"]
        if STATE["orders"] != 200:
            return Resp(STATE["orders"], {"detail": "x"})
        return Resp(200, ORDER)
    if STATE["inventory_down"]:
        raise httpx.ConnectError("sin conexión")
    return Resp(200, PRODUCTS)


resolvers.http_get = fake_http_get

QUERY = """
query { resumenPedido(id: 15) { estado total items { nombre cantidad producto { descripcion disponible } } } }
"""


def setup_function():
    CALLS.clear()
    STATE.update({"orders": 200, "orders_error": None, "inventory_down": False})


def post(query=QUERY, user="7", role="cliente", variables=None, token="tok-gw-graphql"):
    headers = {"X-Service-Token": token, "X-User-Id": user, "X-User-Role": role}
    return client.post("/graphql", json={"query": query, "variables": variables}, headers=headers)


def test_la_consulta_combina_orders_e_inventory():
    r = post()
    assert r.status_code == 200
    data = r.json()["data"]["resumenPedido"]
    assert data["estado"] == "PENDIENTE_PAGO"  # viene de orders
    assert data["items"][0]["producto"]["descripcion"] == "Pasta fresca rellena."  # viene de inventory
    assert data["items"][1]["producto"]["descripcion"] == "Fettuccine fresco."
    assert "errors" not in r.json()


def test_inventory_se_consulta_una_sola_vez_aunque_haya_varios_items():
    post()
    assert len([c for c in CALLS if c[0].endswith("/products")]) == 1


def test_orders_recibe_la_identidad_verificada_y_su_credencial():
    post(user="7", role="cliente")
    url, headers = [c for c in CALLS if "/orders/" in c[0]][0]
    assert headers["X-User-Id"] == "7"
    assert headers["X-User-Role"] == "cliente"
    assert headers["X-Service-Token"] == "tok-graphql-orders"


def test_inventory_recibe_solo_su_credencial_de_lectura():
    post()
    headers = [c for c in CALLS if c[0].endswith("/products")][0][1]
    assert headers["X-Service-Token"] == "tok-graphql-inventory"
    assert "X-User-Id" not in headers


def test_cliente_no_obtiene_la_direccion():
    r = post("query { resumenPedido(id: 15) { estado direccionEntrega } }", role="cliente")
    body = r.json()
    assert body["data"]["resumenPedido"]["direccionEntrega"] is None
    assert body["data"]["resumenPedido"]["estado"] == "PENDIENTE_PAGO"
    assert "No autorizado" in body["errors"][0]["message"]
    assert "Calle Falsa" not in r.text


def test_admin_si_obtiene_la_direccion():
    r = post("query { resumenPedido(id: 15) { direccionEntrega } }", user="1", role="admin")
    assert r.json()["data"]["resumenPedido"]["direccionEntrega"] == "Calle Falsa 123, Paine"


def test_si_inventory_cae_el_pedido_igual_se_entrega_con_error_parcial():
    STATE["inventory_down"] = True
    body = post().json()
    data = body["data"]["resumenPedido"]
    assert data["estado"] == "PENDIENTE_PAGO"
    assert data["items"][0]["producto"] is None
    assert body["errors"]


def test_pedido_ajeno_no_filtra_datos():
    STATE["orders"] = 403
    r = post()
    assert r.json()["data"]["resumenPedido"] is None
    assert "No tienes acceso" in r.json()["errors"][0]["message"]
    assert "Calle Falsa" not in r.text and "Ravioles" not in r.text


def test_pedido_inexistente():
    STATE["orders"] = 404
    assert "no encontrado" in post().json()["errors"][0]["message"]


def test_orders_caido_da_error_controlado():
    STATE["orders_error"] = httpx.ConnectError("sin conexión")
    body = post().json()
    assert body["data"]["resumenPedido"] is None
    assert "no está disponible" in body["errors"][0]["message"]


def test_errores_inesperados_se_ocultan():
    STATE["orders_error"] = RuntimeError("detalle-secreto-interno")
    r = post()
    assert r.status_code == 200
    assert "detalle-secreto-interno" not in r.text
    assert r.json()["errors"][0]["message"] == "Error interno"


def test_sin_credencial_de_servicio_es_401():
    assert post(token="falso").status_code == 401
    assert client.post("/graphql", json={"query": QUERY}).status_code == 401


def test_sin_identidad_o_rol_invalido_es_401():
    h = {"X-Service-Token": "tok-gw-graphql"}
    assert client.post("/graphql", json={"query": QUERY}, headers=h).status_code == 401
    assert post(role="superadmin").status_code == 401


def test_introspeccion_deshabilitada():
    r = post("query { __schema { types { name } } }")
    assert r.status_code == 400
    assert "introspección" in r.text


def test_limite_de_profundidad(monkeypatch=None):
    anterior = limits.MAX_DEPTH
    limits.MAX_DEPTH = 3
    try:
        assert post().status_code == 400  # la consulta tiene 4 niveles
    finally:
        limits.MAX_DEPTH = anterior
    assert post().status_code == 200


def test_limite_de_costo_contra_alias_masivos():
    aliases = " ".join(f"a{i}: resumenPedido(id: 15) {{ id }}" for i in range(60))
    assert post(f"query {{ {aliases} }}").status_code == 400
    assert CALLS == []


def test_mutaciones_no_existen():
    assert post("mutation { x }").status_code == 400


def test_campo_inexistente_o_restringido_no_pedible():
    assert post("query { resumenPedido(id: 15) { clienteId } }").status_code == 400


def test_consulta_demasiado_larga():
    assert post("query { resumenPedido(id: 15) { id } }" + " " * 2500).status_code == 400


def test_variables_funcionan():
    q = "query($id: Int!) { resumenPedido(id: $id) { estado } }"
    assert post(q, variables={"id": 15}).json()["data"]["resumenPedido"]["estado"] == "PENDIENTE_PAGO"
