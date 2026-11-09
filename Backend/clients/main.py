import secrets
import sqlite3
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import get_conn, init_db
from secrets_provider import get_secret

app = FastAPI(title="clients")
init_db()

# Quién puede llamar a este servicio: una credencial distinta por llamador
TOKENS = {
    "gateway": get_secret("GW_CLIENTS"),
    "auth": get_secret("AUTH_CLIENTS"),
}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Datos inválidos"})


def allow(*callers):
    """Exige un X-Service-Token válido y que ese llamador esté permitido en la ruta."""

    def check(x_service_token: Optional[str] = Header(None)) -> str:
        if not x_service_token:
            raise HTTPException(401, "No autorizado")
        for name, token in TOKENS.items():
            if secrets.compare_digest(x_service_token.encode(), token.encode()):
                if name not in callers:
                    raise HTTPException(403, "Llamador no permitido en esta ruta")
                return name
        raise HTTPException(401, "No autorizado")

    return check


def current_client(
    x_user_id: Optional[str] = Header(None), x_user_role: Optional[str] = Header(None)
) -> int:
    """Identidad verificada por el gateway. Solo se confía porque la ruta exige al gateway."""
    if not x_user_id or not x_user_id.isdigit():
        raise HTTPException(401, "No autorizado")
    if x_user_role != "cliente":
        raise HTTPException(403, "Solo los clientes tienen perfil")
    return int(x_user_id)


class ProfileCreate(BaseModel):
    credencialId: int
    nombre: str = Field(min_length=1, max_length=100)
    email: str = Field(max_length=254)
    telefono: Optional[str] = Field(default=None, max_length=20)


class ProfileUpdate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    telefono: Optional[str] = Field(default=None, max_length=20)


def to_dto(row) -> dict:
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "email": row["email"],
        "telefono": row["telefono"],
    }


def find(conn, client_id: int):
    row = conn.execute("SELECT * FROM clientes WHERE id = ?", (client_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Perfil no encontrado")
    return row


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- S05: ver mi perfil ----------
@app.get("/clients/me", dependencies=[Depends(allow("gateway"))])
def get_me(client_id: int = Depends(current_client)):
    with get_conn() as conn:
        return to_dto(find(conn, client_id))


# ---------- S06: editar mi perfil (el correo no se cambia aquí) ----------
@app.put("/clients/me", dependencies=[Depends(allow("gateway"))])
def update_me(body: ProfileUpdate, client_id: int = Depends(current_client)):
    with get_conn() as conn:
        find(conn, client_id)
        conn.execute(
            "UPDATE clientes SET nombre = ?, telefono = ? WHERE id = ?",
            (body.nombre, body.telefono, client_id),
        )
        return to_dto(find(conn, client_id))


# ---------- Ruta interna: solo la puede llamar Auth al registrar ----------
@app.post("/internal/clients", status_code=201, dependencies=[Depends(allow("auth"))])
def create_client(body: ProfileCreate):
    with get_conn() as conn:
        try:
            conn.execute(
                "INSERT INTO clientes (id, nombre, email, telefono) VALUES (?, ?, ?, ?)",
                (body.credencialId, body.nombre, body.email, body.telefono),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(409, "El perfil ya existe")
        return to_dto(find(conn, body.credencialId))
