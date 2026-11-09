import os
import tempfile

import httpx

# Se configura el entorno ANTES de importar la app
os.environ["AUTH_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GW_AUTH"] = "tok-gw-auth"
os.environ["AUTH_CLIENTS"] = "tok-auth-clients"
os.environ["JWT_SIGNING"] = "clave-de-prueba-de-al-menos-32-caracteres!!"
os.environ["ADMIN_EMAIL"] = "admin@example.com"
os.environ["ADMIN_PASSWORD"] = "AdminDePrueba123"

import jwt  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from db import get_conn  # noqa: E402

client = TestClient(main.app)
GW = {"X-Service-Token": "tok-gw-auth"}
KEY = os.environ["JWT_SIGNING"]


def registrar(email, extra=None):
    body = {"nombre": "Ana", "email": email, "password": "ClaveDePrueba123"}
    body.update(extra or {})
    return client.post("/register", json=body, headers=GW)


def setup_function():
    main.create_profile = lambda *a, **k: None  # clients aún no se usa en estas pruebas


def test_registro_ok_sin_password_en_respuesta():
    r = registrar("ana@example.com")
    assert r.status_code == 201
    assert "password" not in r.json()
    assert r.json()["email"] == "ana@example.com"


def test_correo_duplicado_es_409():
    registrar("dup@example.com")
    assert registrar("dup@example.com").status_code == 409


def test_sin_token_de_servicio_es_401():
    body = {"nombre": "Ana", "email": "x@example.com", "password": "ClaveDePrueba123"}
    assert client.post("/register", json=body).status_code == 401


def test_password_corta_es_400():
    body = {"nombre": "Ana", "email": "corta@example.com", "password": "123"}
    assert client.post("/register", json=body, headers=GW).status_code == 400


def test_password_se_guarda_con_hash():
    registrar("hash@example.com")
    with get_conn() as conn:
        row = conn.execute("SELECT password_hash FROM credenciales WHERE email = 'hash@example.com'").fetchone()
    assert row["password_hash"].startswith("scrypt$")
    assert "ClaveDePrueba123" not in row["password_hash"]


def test_login_ok_entrega_token_de_cliente():
    registrar("login@example.com")
    r = client.post("/login", json={"email": "login@example.com", "password": "ClaveDePrueba123"}, headers=GW)
    assert r.status_code == 200
    data = jwt.decode(r.json()["accessToken"], KEY, algorithms=["HS256"])
    assert data["role"] == "cliente"
    assert r.json()["expiresIn"] == 1800


def test_login_incorrecto_da_el_mismo_error_si_el_correo_no_existe():
    registrar("real@example.com")
    mala = client.post("/login", json={"email": "real@example.com", "password": "incorrecta1"}, headers=GW)
    nadie = client.post("/login", json={"email": "nadie@example.com", "password": "incorrecta1"}, headers=GW)
    assert mala.status_code == nadie.status_code == 401
    assert mala.json() == nadie.json()


def test_el_rol_no_se_puede_elegir_al_registrarse():
    registrar("intruso@example.com", {"rol": "admin"})
    r = client.post("/login", json={"email": "intruso@example.com", "password": "ClaveDePrueba123"}, headers=GW)
    assert jwt.decode(r.json()["accessToken"], KEY, algorithms=["HS256"])["role"] == "cliente"


def test_admin_sembrado_entra_con_rol_admin():
    r = client.post("/login", json={"email": "admin@example.com", "password": "AdminDePrueba123"}, headers=GW)
    assert jwt.decode(r.json()["accessToken"], KEY, algorithms=["HS256"])["role"] == "admin"


def test_si_clients_falla_no_queda_credencial_huerfana():
    def falla(*a, **k):
        raise httpx.ConnectError("sin conexión")

    main.create_profile = falla
    assert registrar("huerfano@example.com").status_code == 503
    main.create_profile = lambda *a, **k: None
    assert registrar("huerfano@example.com").status_code == 201
