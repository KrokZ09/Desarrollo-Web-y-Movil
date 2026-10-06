from fastapi import FastAPI
import httpx

app = FastAPI(title= "Local API Gateway")

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

