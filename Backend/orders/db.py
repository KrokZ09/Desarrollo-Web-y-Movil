import os
import sqlite3

DB_PATH = os.environ.get("ORDERS_DB", "orders.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                estado TEXT NOT NULL,
                total INTEGER NOT NULL,
                direccion_entrega TEXT NOT NULL,
                creado_en TEXT NOT NULL
            )
            """
        )
        # El detalle guarda copia de nombre y precio: el historial no cambia si el catálogo cambia
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS detalles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL REFERENCES pedidos(id),
                producto_id INTEGER NOT NULL,
                nombre_producto TEXT NOT NULL,
                precio_unitario INTEGER NOT NULL,
                cantidad INTEGER NOT NULL
            )
            """
        )
