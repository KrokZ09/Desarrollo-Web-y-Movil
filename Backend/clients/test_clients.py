import os
import tempfile

# Se configura el entorno ANTES de importar la app
os.environ["CLIENTS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GW_CLIENTS"] = "tok-gw-clients"
os.environ["AUTH_CLIENTS"] = "tok-auth-clients"

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402

client = TestClient(app)
AUTH = {"X-Service-Token": "tok-auth-clients"}


def gw(user_id, role="cliente"):
    return {"X-Service-Token": "tok-gw-clients", "X-User-Id": str(user_id), "X-User-Role": role}


def crear(cred_id, email, nombre="Ana"):
    body = {"credencialId": cred_id, "nombre": nombre, "email": email, "telefono": "+56911111111"}
    return client.post("/internal/clients", json=body, headers=AUTH)


def test_auth_crea_perfil():
    assert crear(10, "a10@example.com").status_code == 201


def test_perfil_duplicado_es_409():
    crear(11, "a11@example.com")
    assert crear(11, "otro@example.com").status_code == 409


def test_cada_cliente_ve_solo_su_perfil():
    crear(20, "a20@example.com", "Uno")
    crear(21, "a21@example.com", "Dos")
    assert client.get("/clients/me", headers=gw(20)).json()["email"] == "a20@example.com"
    assert client.get("/clients/me", headers=gw(21)).json()["email"] == "a21@example.com"


def test_perfil_inexistente_es_404():
    assert client.get("/clients/me", headers=gw(999)).status_code == 404


def test_sin_identidad_es_401():
    h = {"X-Service-Token": "tok-gw-clients"}
    assert client.get("/clients/me", headers=h).status_code == 401


def test_admin_no_tiene_perfil_de_cliente():
    assert client.get("/clients/me", headers=gw(1, "admin")).status_code == 403


def test_sin_token_de_servicio_es_401():
    assert client.get("/clients/me").status_code == 401


def test_gateway_no_puede_usar_la_ruta_interna():
    body = {"credencialId": 30, "nombre": "X", "email": "x@example.com"}
    assert client.post("/internal/clients", json=body, headers=gw(30)).status_code == 403


def test_auth_no_puede_leer_perfiles():
    assert client.get("/clients/me", headers=AUTH).status_code == 403


def test_editar_perfil_no_cambia_el_correo():
    crear(40, "a40@example.com")
    r = client.put("/clients/me", json={"nombre": "Nuevo", "telefono": "+56922222222"}, headers=gw(40))
    assert r.status_code == 200
    assert r.json()["nombre"] == "Nuevo"
    assert r.json()["email"] == "a40@example.com"


def test_nombre_vacio_es_400():
    crear(41, "a41@example.com")
    assert client.put("/clients/me", json={"nombre": ""}, headers=gw(41)).status_code == 400
