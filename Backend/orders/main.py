import os
import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import get_conn, init_db
from secrets_provider import get_secret

app = FastAPI(title="orders")
init_db()

# Quién puede llamar a este servicio: una credencial distinta por llamador
TOKENS = {
    "gateway": get_secret("GW_ORDERS"),
    "payments": get_secret("PAYMENTS_ORDERS"),
    "graphql": get_secret("GRAPHQL_ORDERS"),
}
INVENTORY_TOKEN = get_secret("ORDERS_INVENTORY")  # credencial para llamar a inventory
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://127.0.0.1:8003")

Estado = Literal["PENDIENTE_PAGO", "PAGADO", "EN_PREPARACION", "DESPACHADO", "ENTREGADO", "ANULADO"]

# Transiciones que puede pedir un admin (S17). PENDIENTE_PAGO -> PAGADO solo lo hace payments.
TRANSICIONES_ADMIN = {
    "PENDIENTE_PAGO": {"ANULADO"},
    "PAGADO": {"EN_PREPARACION", "ANULADO"},
    "EN_PREPARACION": {"DESPACHADO"},
    "DESPACHADO": {"ENTREGADO"},
}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Datos inválidos"})


# ---------- Seguridad ----------
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


def current_user(
    x_user_id: Optional[str] = Header(None), x_user_role: Optional[str] = Header(None)
) -> tuple:
    """Identidad verificada por el gateway (solo se confía porque la ruta exige al gateway)."""
    if not x_user_id or not x_user_id.isdigit():
        raise HTTPException(401, "No autorizado")
    if x_user_role not in ("cliente", "admin"):
        raise HTTPException(403, "Rol no permitido")
    return int(x_user_id), x_user_role


def require_role(role: str):
    def check(user: tuple = Depends(current_user)) -> int:
        if user[1] != role:
            raise HTTPException(403, "Rol no permitido para esta operación")
        return user[0]

    return check


# ---------- Modelos ----------
class ItemIn(BaseModel):
    productId: int
    cantidad: int = Field(ge=1, le=20)


class OrderIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, max_length=20)
    direccionEntrega: str = Field(min_length=5, max_length=200)


class StatusIn(BaseModel):
    estado: Estado


# ---------- Utilidades ----------
def call_inventory(path: str, items: list):
    """Llama a inventory con plazo de 3 s. Si no responde, el error es 503 (falla cerrado)."""
    try:
        r = httpx.post(
            f"{INVENTORY_URL}{path}",
            json={"items": items},
            headers={"X-Service-Token": INVENTORY_TOKEN},
            timeout=3.0,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    if r.status_code in (409, 422):
        raise HTTPException(r.status_code, r.json().get("detail", "Error de inventario"))
    if r.status_code != 200:
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    return r.json()


def load(conn, order_id: int):
    p = conn.execute("SELECT * FROM pedidos WHERE id = ?", (order_id,)).fetchone()
    if not p:
        raise HTTPException(404, "Pedido no encontrado")
    items = conn.execute("SELECT * FROM detalles WHERE pedido_id = ?", (order_id,)).fetchall()
    return p, items


def dto(p, items, with_owner: bool = False) -> dict:
    out = {
        "id": p["id"],
        "estado": p["estado"],
        "total": p["total"],
        "direccionEntrega": p["direccion_entrega"],
        "creadoEn": p["creado_en"],
        "items": [
            {
                "productId": i["producto_id"],
                "nombre": i["nombre_producto"],
                "precioUnitario": i["precio_unitario"],
                "cantidad": i["cantidad"],
            }
            for i in items
        ],
    }
    if with_owner:
        out["clienteId"] = p["cliente_id"]
    return out


def summary(p, with_owner: bool = False) -> dict:
    out = {"id": p["id"], "estado": p["estado"], "total": p["total"], "creadoEn": p["creado_en"]}
    if with_owner:
        out["clienteId"] = p["cliente_id"]
    return out


def check_owner(p, user_id: int, role: str):
    if role == "cliente" and p["cliente_id"] != user_id:
        raise HTTPException(403, "No tienes acceso a este pedido")


def cancel(order_id: int, allowed: set) -> dict:
    """Anula (no borra) y devuelve el stock. Si inventory falla, el pedido no cambia."""
    with get_conn() as conn:
        p, items = load(conn, order_id)
        if p["estado"] not in allowed:
            raise HTTPException(409, "El pedido no se puede anular en su estado actual")
        cur = conn.execute(
            "UPDATE pedidos SET estado = 'ANULADO' WHERE id = ? AND estado = ?",
            (order_id, p["estado"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "El pedido cambió de estado, intenta de nuevo")
        release = [{"productId": i["producto_id"], "cantidad": i["cantidad"]} for i in items]
        call_inventory("/internal/stock/release", release)  # si falla, se revierte el UPDATE
        return dto(*load(conn, order_id))


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- S07: crear pedido ----------
@app.post("/orders", status_code=201, dependencies=[Depends(allow("gateway"))])
def create_order(body: OrderIn, user_id: int = Depends(require_role("cliente"))):
    merged = {}
    for it in body.items:
        merged[it.productId] = merged.get(it.productId, 0) + it.cantidad
    if any(c > 20 for c in merged.values()):
        raise HTTPException(400, "Cantidad máxima por producto: 20")
    items = [{"productId": k, "cantidad": v} for k, v in merged.items()]

    reserved = call_inventory("/internal/stock/reserve", items)
    # El precio y el total los calcula el servidor con los datos de inventory
    total = sum(r["precioUnitario"] * r["cantidad"] for r in reserved)
    try:
        with get_conn() as conn:
            cur = conn.execute(
                "INSERT INTO pedidos (cliente_id, estado, total, direccion_entrega, creado_en) "
                "VALUES (?, 'PENDIENTE_PAGO', ?, ?, ?)",
                (
                    user_id,
                    total,
                    body.direccionEntrega,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
            )
            order_id = cur.lastrowid
            conn.executemany(
                "INSERT INTO detalles (pedido_id, producto_id, nombre_producto, precio_unitario, cantidad) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (order_id, r["productId"], r["nombre"], r["precioUnitario"], r["cantidad"])
                    for r in reserved
                ],
            )
            return dto(*load(conn, order_id))
    except Exception:
        try:  # si no se pudo guardar el pedido, se devuelve el stock reservado
            call_inventory("/internal/stock/release", items)
        except HTTPException:
            pass
        raise


# ---------- S08: mis pedidos ----------
@app.get("/orders", dependencies=[Depends(allow("gateway"))])
def my_orders(
    user_id: int = Depends(require_role("cliente")),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM pedidos WHERE cliente_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, size, (page - 1) * size),
        ).fetchall()
    return [summary(r) for r in rows]


# ---------- S09: detalle de pedido (también lo usa el GraphQL Gateway con la misma identidad) ----------
@app.get("/orders/{order_id}", dependencies=[Depends(allow("gateway", "graphql"))])
def get_order(order_id: int, user: tuple = Depends(current_user)):
    with get_conn() as conn:
        p, items = load(conn, order_id)
    check_owner(p, user[0], user[1])
    return dto(p, items)


# ---------- S10: anular pedido propio (no se borra el registro) ----------
@app.delete("/orders/{order_id}", dependencies=[Depends(allow("gateway"))])
def cancel_order(order_id: int, user_id: int = Depends(require_role("cliente"))):
    with get_conn() as conn:
        p, _ = load(conn, order_id)
    check_owner(p, user_id, "cliente")
    return cancel(order_id, {"PENDIENTE_PAGO"})


# ---------- S16: todos los pedidos (admin) ----------
@app.get(
    "/admin/orders",
    dependencies=[Depends(allow("gateway")), Depends(require_role("admin"))],
)
def admin_orders(
    estado: Optional[Estado] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=50),
):
    sql, params = "SELECT * FROM pedidos", []
    if estado:
        sql, params = sql + " WHERE estado = ?", [estado]
    with get_conn() as conn:
        rows = conn.execute(
            sql + " ORDER BY id DESC LIMIT ? OFFSET ?", params + [size, (page - 1) * size]
        ).fetchall()
    return [summary(r, with_owner=True) for r in rows]


# ---------- S17: cambiar estado (admin) ----------
@app.put(
    "/orders/{order_id}/status",
    dependencies=[Depends(allow("gateway")), Depends(require_role("admin"))],
)
def change_status(order_id: int, body: StatusIn):
    with get_conn() as conn:
        p, _ = load(conn, order_id)
    if body.estado not in TRANSICIONES_ADMIN.get(p["estado"], set()):
        raise HTTPException(409, "Transición de estado no permitida")
    if body.estado == "ANULADO":
        return cancel(order_id, {p["estado"]})
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE pedidos SET estado = ? WHERE id = ? AND estado = ?",
            (body.estado, order_id, p["estado"]),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "El pedido cambió de estado, intenta de nuevo")
        return dto(*load(conn, order_id))


# ---------- Rutas internas: solo payments ----------
@app.get("/internal/orders/{order_id}", dependencies=[Depends(allow("payments"))])
def internal_get_order(order_id: int):
    with get_conn() as conn:
        return dto(*load(conn, order_id), with_owner=True)


@app.post("/internal/orders/{order_id}/mark-paid", dependencies=[Depends(allow("payments"))])
def mark_paid(order_id: int):
    with get_conn() as conn:
        p, items = load(conn, order_id)
        if p["estado"] == "PAGADO":
            return dto(p, items)  # repetido: no cambia nada
        if p["estado"] != "PENDIENTE_PAGO":
            raise HTTPException(409, "El pedido no admite pago en su estado actual")
        cur = conn.execute(
            "UPDATE pedidos SET estado = 'PAGADO' WHERE id = ? AND estado = 'PENDIENTE_PAGO'",
            (order_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(409, "El pedido cambió de estado, intenta de nuevo")
        return dto(*load(conn, order_id))
