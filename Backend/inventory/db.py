import os
import sqlite3

DB_PATH = os.environ.get("INVENTORY_DB", "inventory.db")

# Datos de prueba ficticios (los precios son inventados)
SEED = [
    ("Ravioles", "Pasta fresca rellena, lista para cocinar.", 5900, 50),
    ("Fettuccine", "Fettuccine fresco.", 4500, 50),
    ("Ñoquis", "Ñoquis frescos, listos para cocinar.", 4800, 50),
    ("Lasaña", "Láminas frescas para preparar una lasaña casera.", 5200, 50),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT NOT NULL,
                precio INTEGER NOT NULL CHECK (precio >= 0),
                disponible INTEGER NOT NULL DEFAULT 1,
                stock INTEGER NOT NULL DEFAULT 0 CHECK (stock >= 0)
            )
            """
        )
        if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            conn.executemany(
                "INSERT INTO products (nombre, descripcion, precio, stock) VALUES (?, ?, ?, ?)",
                SEED,
            )
