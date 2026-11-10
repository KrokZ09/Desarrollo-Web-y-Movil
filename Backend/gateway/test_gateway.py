import os
import time

import httpx

# Se configura el entorno ANTES de importar la app
KEY = "clave-de-prueba-de-al-menos-32-caracteres!!"
os.environ["JWT_SIGNING"] = KEY
for name in ("AUTH", "CLIENTS", "INVENTORY", "ORDERS", "PAYMENTS", "GRAPHQL"):
    os.environ[f"GW_{name}"] = f"tok-{name.lower()}"

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from policies import RateLimitPolicy  # noqa: E402

client = TestClient(main.app)
CALLS = []
STATE = {"status": 200, "error": None}


class FakeResponse:
    def __init__(self, status, content=b'{"ok": true}'):
        self.status_code = status
        self.content = content
        self.headers = {"content-type": "application/json"}


async def fake_forward(method, url, headers, content, params):
    """Simula los servicios internos y guarda lo que el gateway les envió."""
    if STATE["error"]:
        raise STATE["error"]
    CALLS.append({"method": method, "url": url, "headers": headers, "content": content, "params": params})
    return FakeResponse(STATE["status"])


main.forward = fake_forward


def setup_function():
    CALLS.clear()
    STATE["status"], STATE["error"] = 200, None
    main.limiter = RateLimitPolicy()


def token(user_id="7", role="cliente", exp=600, key=KEY):
    payload = {"sub": user_id, "role": role, "exp": int(time.time()) + exp}
    return {"Authorization": f"Bearer {jwt.encode(payload, key, algorithm='HS256')}"}


def test_catalogo_es_publico_y_llega_con_credencial_de_servicio():
    r = client.get("/api/v1/products?available=true")
    assert r.status_code == 200
    call = CALLS[0]
    assert call["url"] == "http://127.0.0.1:8003/products"
    assert call["params"] == [("available", "true")]
    assert call["headers"]["X-Service-Token"] == "tok-inventory"
    assert "X-User-Id" not in call["headers"]


def test_ruta_no_listada_es_404_y_no_se_reenvia():
    for method, path in [
        ("GET", "/api/v1/internal/stock/reserve"),
        ("POST", "/internal/stock/reserve"),
        ("GET", "/internal/orders/1"),
        ("DELETE", "/api/v1/products/1"),
        ("GET", "/api/v1/orders/abc"),
    ]:
        assert client.request(method, path, headers=token()).status_code == 404
    assert CALLS == []


def test_ruta_protegida_sin_token_es_401():
    assert client.get("/api/v1/orders").status_code == 401
    assert CALLS == []


def test_token_firmado_con_otra_clave_es_401():
    h = token(key="otra-clave-distinta-de-al-menos-32-caracteres")
    assert client.get("/api/v1/orders", headers=h).status_code == 401


def test_token_expirado_es_401():
    assert client.get("/api/v1/orders", headers=token(exp=-10)).status_code == 401


def test_token_sin_firma_alg_none_es_401():
    payload = {"sub": "1", "role": "admin", "exp": int(time.time()) + 600}
    h = {"Authorization": f"Bearer {jwt.encode(payload, '', algorithm='none')}"}
    assert client.get("/api/v1/admin/orders", headers=h).status_code == 401
    assert CALLS == []


def test_rol_desconocido_es_401():
    assert client.get("/api/v1/orders", headers=token(role="superadmin")).status_code == 401


def test_cliente_en_ruta_de_admin_es_403():
    r = client.put("/api/v1/products/1", json={"nombre": "x"}, headers=token(role="cliente"))
    assert r.status_code == 403
    assert CALLS == []


def test_admin_pasa_a_ruta_de_admin():
    r = client.get("/api/v1/admin/orders", headers=token("1", "admin"))
    assert r.status_code == 200
    assert CALLS[0]["headers"]["X-User-Role"] == "admin"


def test_cabeceras_de_identidad_falsas_se_descartan():
    h = {**token("7", "cliente"), "X-User-Id": "999", "X-User-Role": "admin", "X-Service-Token": "malo"}
    client.get("/api/v1/orders", headers=h)
    sent = CALLS[0]["headers"]
    assert sent["X-User-Id"] == "7"
    assert sent["X-User-Role"] == "cliente"
    assert sent["X-Service-Token"] == "tok-orders"


def test_el_token_del_usuario_no_se_reenvia():
    client.get("/api/v1/orders", headers=token())
    assert "Authorization" not in CALLS[0]["headers"]
    assert "authorization" not in CALLS[0]["headers"]


def test_la_propiedad_la_decide_el_servicio_no_el_gateway():
    assert client.get("/api/v1/orders/15", headers=token("8")).status_code == 200
    assert CALLS[0]["url"] == "http://127.0.0.1:8004/orders/15"
    assert CALLS[0]["headers"]["X-User-Id"] == "8"


def test_webhook_pasa_sin_sesion_y_reenvia_firma_y_cuerpo_exacto():
    raw = b'{"eventId":"e1","orderId":15,"status":"PAID"}'
    r = client.post("/api/v1/payments/webhook", content=raw, headers={"X-Signature": "abc123"})
    assert r.status_code == 200
    assert CALLS[0]["content"] == raw
    assert CALLS[0]["headers"]["X-Signature"] == "abc123"
    assert CALLS[0]["headers"]["X-Service-Token"] == "tok-payments"


def test_graphql_exige_sesion_y_reenvia_identidad():
    assert client.post("/api/v1/graphql", json={"query": "{ x }"}).status_code == 401
    client.post("/api/v1/graphql", json={"query": "{ x }"}, headers=token("7"))
    assert CALLS[0]["url"] == "http://127.0.0.1:8006/graphql"
    assert CALLS[0]["headers"]["X-User-Id"] == "7"


def test_login_tiene_limite_de_intentos():
    codes = [client.post("/api/v1/auth/login", json={"email": "a@b.cl", "password": "x"}).status_code for _ in range(11)]
    assert codes[:10] == [200] * 10
    assert codes[10] == 429


def test_servicio_caido_es_503_y_lento_es_504():
    STATE["error"] = httpx.ConnectError("sin conexión")
    assert client.get("/api/v1/products").status_code == 503
    STATE["error"] = httpx.ReadTimeout("lento")
    assert client.get("/api/v1/products").status_code == 504


def test_cuerpo_demasiado_grande_es_413():
    r = client.post("/api/v1/auth/login", content=b"x" * (70 * 1024))
    assert r.status_code == 413
    assert CALLS == []


def test_si_un_servicio_rechaza_al_gateway_el_usuario_ve_502():
    STATE["status"] = 401
    assert client.get("/api/v1/orders", headers=token()).status_code == 502


def test_login_incorrecto_de_auth_se_entrega_como_401():
    STATE["status"] = 401
    assert client.post("/api/v1/auth/login", json={"email": "a@b.cl", "password": "x"}).status_code == 401


def test_cada_respuesta_trae_identificador_de_correlacion():
    r = client.get("/api/v1/products")
    assert r.headers["X-Correlation-Id"] == CALLS[0]["headers"]["X-Correlation-Id"]
