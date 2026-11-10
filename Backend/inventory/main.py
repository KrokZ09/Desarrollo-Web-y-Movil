import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from db import get_conn, init_db
from secrets_provider import get_secret

app = FastAPI(title="inventory")
init_db()

# Quién puede llamar a este servicio: una credencial distinta por llamador
TOKENS = {
    "gateway": get_secret("GW_INVENTORY"),
    "orders": get_secret("ORDERS_INVENTORY"),
    "graphql": get_secret("GRAPHQL_INVENTORY"),
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


def admin_only(x_user_role: Optional[str] = Header(None)):
    # Esta cabecera solo es confiable porque la ruta exige que llame el gateway
    if x_user_role != "admin":
        raise HTTPException(403, "Requiere rol admin")


class ProductIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str = Field(min_length=1, max_length=300)
    precio: int = Field(ge=0)
    stock: int = Field(ge=0)


class ProductUpdate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str = Field(min_length=1, max_length=300)
    precio: int = Field(ge=0)
    disponible: bool


class StockIn(BaseModel):
    stock: int = Field(ge=0)


class Item(BaseModel):
    productId: int
    cantidad: int = Field(ge=1, le=20)


class Items(BaseModel):
    items: list[Item] = Field(min_length=1)


def public(row) -> dict:
    """Solo campos públicos: el stock no sale en el catálogo."""
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "descripcion": row["descripcion"],
        "precio": row["precio"],
        "disponible": bool(row["disponible"]),
    }


def get_or_404(conn, product_id: int):
    row = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Producto no encontrado")
    return row


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------- S01, S02: catálogo ----------
@app.get("/products", dependencies=[Depends(allow("gateway", "graphql"))])
def list_products(available: Optional[bool] = None):
    sql, params = "SELECT * FROM products", ()
    if available is not None:
        sql, params = sql + " WHERE disponible = ?", (int(available),)
    with get_conn() as conn:
        return [public(r) for r in conn.execute(sql + " ORDER BY id", params)]


@app.get("/products/{product_id}", dependencies=[Depends(allow("gateway", "graphql"))])
def get_product(product_id: int):
    with get_conn() as conn:
        return public(get_or_404(conn, product_id))


# ---------- S13, S14, S15: administración ----------
@app.post(
    "/products",
    status_code=201,
    dependencies=[Depends(allow("gateway")), Depends(admin_only)],
)
def create_product(body: ProductIn):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO products (nombre, descripcion, precio, stock) VALUES (?, ?, ?, ?)",
            (body.nombre, body.descripcion, body.precio, body.stock),
        )
        return public(get_or_404(conn, cur.lastrowid))


@app.put(
    "/products/{product_id}",
    dependencies=[Depends(allow("gateway")), Depends(admin_only)],
)
def update_product(product_id: int, body: ProductUpdate):
    with get_conn() as conn:
        get_or_404(conn, product_id)
        conn.execute(
            "UPDATE products SET nombre = ?, descripcion = ?, precio = ?, disponible = ? WHERE id = ?",
            (body.nombre, body.descripcion, body.precio, int(body.disponible), product_id),
        )
        return public(get_or_404(conn, product_id))


@app.put(
    "/products/{product_id}/stock",
    dependencies=[Depends(allow("gateway")), Depends(admin_only)],
)
def set_stock(product_id: int, body: StockIn):
    with get_conn() as conn:
        get_or_404(conn, product_id)
        conn.execute("UPDATE products SET stock = ? WHERE id = ?", (body.stock, product_id))
        return {"id": product_id, "stock": body.stock}


# ---------- Rutas internas: solo las puede llamar orders ----------
@app.post("/internal/stock/reserve", dependencies=[Depends(allow("orders"))])
def reserve_stock(body: Items):
    result = []
    # Una sola transacción: si un ítem falla, no se descuenta ninguno
    with get_conn() as conn:
        for it in body.items:
            row = conn.execute("SELECT * FROM products WHERE id = ?", (it.productId,)).fetchone()
            if not row or not row["disponible"]:
                raise HTTPException(422, f"Producto {it.productId} no disponible")
            cur = conn.execute(
                "UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?",
                (it.cantidad, it.productId, it.cantidad),
            )
            if cur.rowcount == 0:
                raise HTTPException(409, f"Stock insuficiente para el producto {it.productId}")
            # El precio lo entrega inventory: orders nunca usa el del navegador
            result.append(
                {
                    "productId": it.productId,
                    "nombre": row["nombre"],
                    "precioUnitario": row["precio"],
                    "cantidad": it.cantidad,
                }
            )
    return result


@app.post("/internal/stock/release", dependencies=[Depends(allow("orders"))])
def release_stock(body: Items):
    with get_conn() as conn:
        for it in body.items:
            conn.execute(
                "UPDATE products SET stock = stock + ? WHERE id = ?",
                (it.cantidad, it.productId),
            )
    return {"released": True}
