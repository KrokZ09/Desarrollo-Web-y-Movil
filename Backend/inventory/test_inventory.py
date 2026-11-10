import os
import tempfile

# Se configura el entorno ANTES de importar la app
os.environ["INVENTORY_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GW_INVENTORY"] = "tok-gw"
os.environ["ORDERS_INVENTORY"] = "tok-orders"
os.environ["GRAPHQL_INVENTORY"] = "tok-graphql"

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)
GW = {"X-Service-Token": "tok-gw"}
ADMIN = {**GW, "X-User-Role": "admin"}
ORDERS = {"X-Service-Token": "tok-orders"}


def test_catalogo_por_gateway_sin_stock():
    r = client.get("/products", headers=GW)
    assert r.status_code == 200
    assert len(r.json()) >= 4
    assert "stock" not in r.json()[0]


def test_sin_token_es_401():
    assert client.get("/products").status_code == 401


def test_token_invalido_es_401():
    assert client.get("/products", headers={"X-Service-Token": "falso"}).status_code == 401


def test_orders_no_puede_leer_catalogo():
    assert client.get("/products", headers=ORDERS).status_code == 403


def test_filtro_invalido_es_400():
    assert client.get("/products?available=quizas", headers=GW).status_code == 400


def test_cliente_no_crea_producto():
    body = {"nombre": "Test", "descripcion": "x", "precio": 100, "stock": 1}
    assert client.post("/products", json=body, headers=GW).status_code == 403


def test_admin_crea_producto():
    body = {"nombre": "Test", "descripcion": "x", "precio": 100, "stock": 1}
    r = client.post("/products", json=body, headers=ADMIN)
    assert r.status_code == 201
    assert "stock" not in r.json()


def test_reserva_es_atomica():
    client.put("/products/1/stock", json={"stock": 1}, headers=ADMIN)
    client.put("/products/2/stock", json={"stock": 0}, headers=ADMIN)
    items = [{"productId": 1, "cantidad": 1}, {"productId": 2, "cantidad": 1}]
    assert client.post("/internal/stock/reserve", json={"items": items}, headers=ORDERS).status_code == 409
    # Si el producto 1 se hubiera descontado, esta reserva fallaría
    ok = client.post("/internal/stock/reserve", json={"items": items[:1]}, headers=ORDERS)
    assert ok.status_code == 200
    assert ok.json()[0]["precioUnitario"] == 5900


def test_liberar_devuelve_stock():
    client.put("/products/3/stock", json={"stock": 1}, headers=ADMIN)
    item = {"items": [{"productId": 3, "cantidad": 1}]}
    assert client.post("/internal/stock/reserve", json=item, headers=ORDERS).status_code == 200
    assert client.post("/internal/stock/reserve", json=item, headers=ORDERS).status_code == 409
    client.post("/internal/stock/release", json=item, headers=ORDERS)
    assert client.post("/internal/stock/reserve", json=item, headers=ORDERS).status_code == 200


def test_gateway_no_puede_usar_rutas_internas():
    item = {"items": [{"productId": 1, "cantidad": 1}]}
    assert client.post("/internal/stock/reserve", json=item, headers=GW).status_code == 403
