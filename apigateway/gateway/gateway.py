import os
import secrets
import httpx

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Response
)

from fastapi.security import(
    HTTPBearer,
    HTTPAuthorizationCredentials
)

app = FastAPI(title= "Local API Gateway")

security = HTTPBearer(
    auto_error=False
)

VAULT_ADDR = os.getenv(
    "VAULT_ADDR", "http://127.0.0.1:8200"
)

VAULT_TOKEN = os.getenv(
    "VAULT_TOKEN"
)

if not VAULT_TOKEN:
    raise RuntimeError(
        "VAULT TOKEN no está configurado"
    )




BACKEND_URL = "http://localhost:9000" # fastapi
BACKEND_URL2 = "http://localhost:9100" # fastapi2

# http://localhost:8000/api/products
@app.get("/api/products")
async def products():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_URL}/products" # http://localhost:8000/api/products
        )
    return response.json()

# http://localhost:8000/api/productos
@app.get("/api/productos")
async def productos():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_URL2}/productos" #http://localhost:8000/api/productos
        )
    return response.json()
    
@app.get("/api/orders")
async def orders():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{BACKEND_URL}/orders" #http://localhost:8000/api/productos
        )
    return response.json()

