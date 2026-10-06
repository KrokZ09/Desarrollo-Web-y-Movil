import os
import secrets


from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Depends
)


app = FastAPI(
    title = "Protected Backend API ingles",
    description = "API ubicada en el localhost enrutada por API gateway /api/products y /api/orders"
)

#SELINUX
INTERNAL_GATEWAY_SECRET = os.getenv(
    "INTERNAL_GATEWAY_SECRET"
)

if not INTERNAL_GATEWAY_SECRET:
    raise RuntimeError(
        "INTERNAL_GATEWAY_SECRET no está configurado"
    )

def verify_gateway(
        x_gateway_secret: str = Header(default="")
):
    valid = secrets.compare_digest(
        x_gateway_secret,
        INTERNAL_GATEWAY_SECRET
    )
    if not valid:
        raise HTTPException(
            status_code=403,
            detail="Solicitud no autorizada desde gateway"
        )



@app.get("/health")
def health():
    return{
        "status": "OK",
        "service": "Backend API"
    }
@app.get("/products")
def products():
    return{
        "products": [
            {"id": 1, "name": "Notebook", "price": 900000},
            {"id": 2, "name": "Monitor", "price": 250000}
        ]
    }
@app.get("/orders")
def orders():
    return{
        "orders": [
            {"id": 1001, "status": "paid"},
            {"id": 1002, "status": "pending"}
        ]
    }