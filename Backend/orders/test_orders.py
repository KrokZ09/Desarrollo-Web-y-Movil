import os
import tempfile

# Se configura el entorno ANTES de importar la app
os.environ["ORDERS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GW_ORDERS"] = "tok-gw-orders"
os.environ["PAYMENTS_ORDERS"] = "tok-payments-orders"
os.environ["GRAPHQL_ORDERS"] = "tok-graphql-orders"
os.environ["ORDERS_INVENTORY"] = "tok-orders-inventory"

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402

client = TestClient(main.app)
PAYMENTS = {"X-Service-Token": "tok-payments-orders"}
PRICES = {1: 5900, 2: 4500}
RELEASED = []
MODE = {"fail": None}


def fake_inventory(path, items):
    """Simula inventory: sin red, con precios fijos y fallos a pedido."""
    if MODE["fail"] == "down":
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    if MODE["fail"] == "nostock":
        raise HTTPException(409, "Stock insuficiente")
    if path.endswith("/release"):
        RELEASED.append(items)
        return {"released": True}
    return [
        {
            "productId": i["productId"],
            "nombre": f"Producto {i['productId']}",
            "precioUnitario": PRICES[i["productId"]],
            "cantidad": i["cantidad"],
        }
        for i in items
    ]


main.call_inventory = fake_inventory


def setup_function():
    MODE["fail"] = None
    RELEASED.clear()


def gw(user_id, role="cliente"):
    return {"X-Service-Token": "tok-gw-orders", "X-User-Id": str(user_id), "X-User-Role": role}


def crear(user_id, items=None, **extra):
    body = {
        "items": items or [{"productId": 1, "cantidad": 2}, {"productId": 2, "cantidad": 1}],
        "direccionEntrega": "Calle Falsa 123, Paine",
    }
    body.update(extra)
    return client.post("/orders", json=body, headers=gw(user_id))


def test_el_servidor_calcula_el_total_e_ignora_el_del_navegador():
    r = crear(1, total=1, estado="PAGADO")
    assert r.status_code == 201
    assert r.json()["total"] == 5900 * 2 + 4500
    assert r.json()["estado"] == "PENDIENTE_PAGO"


def test_cantidad_fuera_de_rango_es_400():
    assert crear(1, [{"productId": 1, "cantidad": 500}]).status_code == 400


def test_sin_stock_es_409_y_no_crea_pedido():
    MODE["fail"] = "nostock"
    assert crear(50).status_code == 409
    assert client.get("/orders", headers=gw(50)).json() == []


def test_inventory_caido_es_503_y_no_crea_pedido():
    MODE["fail"] = "down"
    assert crear(51).status_code == 503
    assert client.get("/orders", headers=gw(51)).json() == []


def test_cliente_solo_ve_sus_pedidos():
    crear(60)
    assert len(client.get("/orders", headers=gw(60)).json()) == 1
    assert client.get("/orders", headers=gw(61)).json() == []


def test_pedido_ajeno_es_403_sin_datos():
    oid = crear(70).json()["id"]
    r = client.get(f"/orders/{oid}", headers=gw(71))
    assert r.status_code == 403
    assert "Calle Falsa" not in r.text
    assert client.get(f"/orders/{oid}", headers=gw(70)).status_code == 200


def test_admin_ve_cualquier_pedido():
    oid = crear(72).json()["id"]
    assert client.get(f"/orders/{oid}", headers=gw(1, "admin")).status_code == 200


def test_anular_propio_pedido_devuelve_stock_y_conserva_registro():
    oid = crear(80).json()["id"]
    r = client.delete(f"/orders/{oid}", headers=gw(80))
    assert r.status_code == 200
    assert r.json()["estado"] == "ANULADO"
    assert len(RELEASED) == 1
    assert client.get(f"/orders/{oid}", headers=gw(80)).status_code == 200


def test_no_se_puede_anular_pedido_ajeno():
    oid = crear(81).json()["id"]
    assert client.delete(f"/orders/{oid}", headers=gw(82)).status_code == 403


def test_no_se_puede_anular_pedido_pagado():
    oid = crear(83).json()["id"]
    client.post(f"/internal/orders/{oid}/mark-paid", headers=PAYMENTS)
    assert client.delete(f"/orders/{oid}", headers=gw(83)).status_code == 409


def test_si_inventory_falla_al_anular_el_pedido_no_cambia():
    oid = crear(84).json()["id"]
    MODE["fail"] = "down"
    assert client.delete(f"/orders/{oid}", headers=gw(84)).status_code == 503
    MODE["fail"] = None
    assert client.get(f"/orders/{oid}", headers=gw(84)).json()["estado"] == "PENDIENTE_PAGO"


def test_mark_paid_es_idempotente():
    oid = crear(90).json()["id"]
    a = client.post(f"/internal/orders/{oid}/mark-paid", headers=PAYMENTS)
    b = client.post(f"/internal/orders/{oid}/mark-paid", headers=PAYMENTS)
    assert a.status_code == b.status_code == 200
    assert b.json()["estado"] == "PAGADO"


def test_no_se_paga_un_pedido_anulado():
    oid = crear(91).json()["id"]
    client.delete(f"/orders/{oid}", headers=gw(91))
    assert client.post(f"/internal/orders/{oid}/mark-paid", headers=PAYMENTS).status_code == 409


def test_el_gateway_no_puede_usar_rutas_internas():
    oid = crear(92).json()["id"]
    assert client.post(f"/internal/orders/{oid}/mark-paid", headers=gw(92)).status_code == 403


def test_payments_no_puede_usar_rutas_de_usuario():
    assert client.get("/orders", headers=PAYMENTS).status_code == 403


def test_payments_lee_el_pedido_con_su_dueno():
    oid = crear(93).json()["id"]
    r = client.get(f"/internal/orders/{oid}", headers=PAYMENTS)
    assert r.status_code == 200
    assert r.json()["clienteId"] == 93


def test_admin_cambia_estado_con_transiciones_validas():
    oid = crear(95).json()["id"]
    client.post(f"/internal/orders/{oid}/mark-paid", headers=PAYMENTS)
    ok = client.put(f"/orders/{oid}/status", json={"estado": "EN_PREPARACION"}, headers=gw(1, "admin"))
    assert ok.status_code == 200
    salto = client.put(f"/orders/{oid}/status", json={"estado": "ENTREGADO"}, headers=gw(1, "admin"))
    assert salto.status_code == 409


def test_admin_no_puede_marcar_pagado_a_mano():
    oid = crear(96).json()["id"]
    r = client.put(f"/orders/{oid}/status", json={"estado": "PAGADO"}, headers=gw(1, "admin"))
    assert r.status_code == 409


def test_cliente_no_puede_cambiar_estado_ni_listar_todo():
    oid = crear(97).json()["id"]
    assert client.put(f"/orders/{oid}/status", json={"estado": "ANULADO"}, headers=gw(97)).status_code == 403
    assert client.get("/admin/orders", headers=gw(97)).status_code == 403


def test_admin_lista_pedidos_con_filtro():
    crear(98)
    r = client.get("/admin/orders?estado=PENDIENTE_PAGO", headers=gw(1, "admin"))
    assert r.status_code == 200
    assert all(p["estado"] == "PENDIENTE_PAGO" for p in r.json())
    assert client.get("/admin/orders?estado=INVENTADO", headers=gw(1, "admin")).status_code == 400


def test_sin_token_o_sin_identidad_es_401():
    assert client.get("/orders").status_code == 401
    assert client.get("/orders", headers={"X-Service-Token": "tok-gw-orders"}).status_code == 401
