import hashlib
import hmac
import os
import secrets
import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError

from db import get_conn, init_db
from secrets_provider import get_secret

app = FastAPI(title="payments")
init_db()

GATEWAY_TOKEN = get_secret("GW_PAYMENTS")  # solo el gateway puede llamar a este servicio
ORDERS_TOKEN = get_secret("PAYMENTS_ORDERS")  # credencial para llamar a orders
WEBHOOK_SECRET = get_secret("PAYMENTS_WEBHOOK_SECRET")  # firma de los avisos del proveedor
ORDERS_URL = os.environ.get("ORDERS_URL", "http://127.0.0.1:8004")


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Datos inválidos"})


def gateway_only(x_service_token: Optional[str] = Header(None)):
    if not x_service_token or not secrets.compare_digest(
        x_service_token.encode(), GATEWAY_TOKEN.encode()
    ):
        raise HTTPException(401, "No autorizado")


def current_client(
    x_user_id: Optional[str] = Header(None), x_user_role: Optional[str] = Header(None)
) -> int:
    """Identidad verificada por el gateway (solo se confía porque la ruta exige al gateway)."""
    if not x_user_id or not x_user_id.isdigit():
        raise HTTPException(401, "No autorizado")
    if x_user_role != "cliente":
        raise HTTPException(403, "Rol no permitido para esta operación")
    return int(x_user_id)


def call_orders(method: str, path: str) -> dict:
    """Llama a orders con plazo de 3 s. Si no responde, el error es 503."""
    try:
        r = httpx.request(
            method, f"{ORDERS_URL}{path}", headers={"X-Service-Token": ORDERS_TOKEN}, timeout=3.0
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    if r.status_code in (404, 409):
        raise HTTPException(r.status_code, r.json().get("detail", "Error de pedidos"))
    if r.status_code != 200:
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    return r.json()


def checkout_url(reference: str) -> str:
    """Adaptador de prueba del proveedor: mismo contrato que uno real (referencia + URL de pago)."""
    return f"https://pagos-prueba.invalid/checkout/{reference}"


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- S11: iniciar pago ----------
@app.post("/orders/{order_id}/payments", status_code=201, dependencies=[Depends(gateway_only)])
def start_payment(order_id: int, user_id: int = Depends(current_client)):
    order = call_orders("GET", f"/internal/orders/{order_id}")
    if order["clienteId"] != user_id:
        raise HTTPException(403, "No tienes acceso a este pedido")
    if order["estado"] != "PENDIENTE_PAGO":
        raise HTTPException(409, "El pedido no admite pago en su estado actual")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM pagos WHERE pedido_id = ? AND estado = 'PENDIENTE' ORDER BY id DESC",
            (order_id,),
        ).fetchone()
        if not row:
            reference = "SIM-" + secrets.token_hex(8)
            # El monto lo toma el servidor del pedido: el navegador no lo envía
            cur = conn.execute(
                "INSERT INTO pagos (pedido_id, cliente_id, estado, monto, referencia, creado_en) "
                "VALUES (?, ?, 'PENDIENTE', ?, ?, ?)",
                (order_id, user_id, order["total"], reference, now()),
            )
            payment_id = cur.lastrowid
        else:
            payment_id, reference = row["id"], row["referencia"]
    return {"paymentId": payment_id, "estado": "PENDIENTE", "urlPago": checkout_url(reference)}


# ---------- S12: aviso del proveedor ----------
class WebhookIn(BaseModel):
    eventId: str = Field(min_length=1, max_length=100)
    orderId: int
    status: Literal["PAID", "FAILED"]
    amount: Optional[int] = Field(default=None, ge=0)


def process_event(event: WebhookIn) -> dict:
    with get_conn() as conn:  # una transacción: si algo falla, el evento no queda registrado
        if conn.execute("SELECT 1 FROM eventos_pago WHERE event_id = ?", (event.eventId,)).fetchone():
            return {"processed": False, "duplicate": True}
        pago = conn.execute(
            "SELECT * FROM pagos WHERE pedido_id = ? AND estado = 'PENDIENTE' ORDER BY id DESC",
            (event.orderId,),
        ).fetchone()
        if not pago:
            raise HTTPException(404, "No hay un pago pendiente para ese pedido")
        if event.status == "PAID" and event.amount is not None and event.amount != pago["monto"]:
            raise HTTPException(409, "El monto no coincide con el pedido")
        try:
            conn.execute(
                "INSERT INTO eventos_pago (event_id, pago_id, recibido_en) VALUES (?, ?, ?)",
                (event.eventId, pago["id"], now()),
            )
        except sqlite3.IntegrityError:  # llegó el mismo aviso en paralelo
            return {"processed": False, "duplicate": True}

        if event.status == "FAILED":
            new_state = "RECHAZADO"
        else:
            try:
                # Solo orders cambia el estado oficial del pedido
                call_orders("POST", f"/internal/orders/{event.orderId}/mark-paid")
                new_state = "APROBADO"
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise  # orders no respondió: se revierte y el proveedor reintenta
                new_state = "REVISION_MANUAL"  # pedido anulado: hay que revisar o devolver el dinero
        conn.execute("UPDATE pagos SET estado = ? WHERE id = ?", (new_state, pago["id"]))
        return {"processed": True}


@app.post("/payments/webhook", dependencies=[Depends(gateway_only)])
async def webhook(request: Request, x_signature: Optional[str] = Header(None)):
    raw = await request.body()
    expected = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    if not x_signature or not hmac.compare_digest(x_signature.encode(), expected.encode()):
        raise HTTPException(401, "Firma inválida")
    try:
        event = WebhookIn.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(400, "Datos inválidos")
    return await run_in_threadpool(process_event, event)
