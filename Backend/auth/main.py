import os
import secrets
import sqlite3
from typing import Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import get_conn, init_db
from secrets_provider import get_secret
from security import TOKEN_SECONDS, create_token, hash_password, verify_password

app = FastAPI(title="auth")
init_db()

GATEWAY_TOKEN = get_secret("GW_AUTH")  # solo el gateway puede llamar a este servicio
CLIENTS_TOKEN = get_secret("AUTH_CLIENTS")  # para crear el perfil en clients
CLIENTS_URL = os.environ.get("CLIENTS_URL", "http://127.0.0.1:8002")
# Hash falso para que login tarde lo mismo si el correo no existe
DUMMY_HASH = hash_password("clave-falsa-para-igualar-tiempos")


def seed_admin():
    """Crea la cuenta de administración desde el .env (el rol nunca viene del navegador)."""
    email = get_secret("ADMIN_EMAIL").lower()
    with get_conn() as conn:
        exists = conn.execute("SELECT 1 FROM credenciales WHERE email = ?", (email,)).fetchone()
        if not exists:
            conn.execute(
                "INSERT INTO credenciales (email, password_hash, rol) VALUES (?, ?, 'admin')",
                (email, hash_password(get_secret("ADMIN_PASSWORD"))),
            )


seed_admin()


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Datos inválidos"})


def gateway_only(x_service_token: Optional[str] = Header(None)):
    if not x_service_token or not secrets.compare_digest(
        x_service_token.encode(), GATEWAY_TOKEN.encode()
    ):
        raise HTTPException(401, "No autorizado")


EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    email: str = Field(pattern=EMAIL_PATTERN, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    telefono: Optional[str] = Field(default=None, max_length=20)


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


def create_profile(credencial_id: int, body: RegisterIn, email: str) -> None:
    """Crea el perfil en clients (clients es la autoridad de esos datos)."""
    r = httpx.post(
        f"{CLIENTS_URL}/internal/clients",
        json={
            "credencialId": credencial_id,
            "nombre": body.nombre,
            "email": email,
            "telefono": body.telefono,
        },
        headers={"X-Service-Token": CLIENTS_TOKEN},
        timeout=3.0,
    )
    r.raise_for_status()


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- S03: registro ----------
@app.post("/register", status_code=201, dependencies=[Depends(gateway_only)])
def register(body: RegisterIn):
    email = body.email.lower()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO credenciales (email, password_hash, rol) VALUES (?, ?, 'cliente')",
                (email, hash_password(body.password)),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "El correo ya está registrado")
        cred_id = cur.lastrowid
    try:
        create_profile(cred_id, body, email)
    except httpx.HTTPError:
        # Sin perfil no dejamos credencial huérfana
        with get_conn() as conn:
            conn.execute("DELETE FROM credenciales WHERE id = ?", (cred_id,))
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    return {"id": cred_id, "nombre": body.nombre, "email": email}


# ---------- S04: login ----------
@app.post("/login", dependencies=[Depends(gateway_only)])
def login(body: LoginIn):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM credenciales WHERE email = ?", (body.email.lower(),)
        ).fetchone()
    ok = verify_password(body.password, row["password_hash"] if row else DUMMY_HASH)
    if not row or not ok:
        raise HTTPException(401, "Credenciales incorrectas")  # mismo mensaje en ambos casos
    return {
        "accessToken": create_token(row["id"], row["rol"]),
        "tokenType": "Bearer",
        "expiresIn": TOKEN_SECONDS,
    }
