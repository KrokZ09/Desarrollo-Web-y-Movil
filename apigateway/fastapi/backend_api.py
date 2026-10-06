from fastapi import FastAPI

app = FastAPI(
    title = "Backend API ingles",
    description = "API ubicada en el localhost enrutada por API gateway /api/products y /api/orders"
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