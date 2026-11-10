import os
import sqlite3

DB_PATH = os.environ.get("PAYMENTS_DB", "payments.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL,
                cliente_id INTEGER NOT NULL,
                estado TEXT NOT NULL CHECK (estado IN ('PENDIENTE', 'APROBADO', 'RECHAZADO', 'REVISION_MANUAL')),
                monto INTEGER NOT NULL,
                referencia TEXT NOT NULL,
                creado_en TEXT NOT NULL
            )
            """
        )
        # Un pedido puede tener varios intentos, pero solo un pago aprobado
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS un_pago_aprobado ON pagos(pedido_id) WHERE estado = 'APROBADO'"
        )
        # Cada aviso del proveedor se registra por eventId: así no se procesa dos veces
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos_pago (
                event_id TEXT PRIMARY KEY,
                pago_id INTEGER NOT NULL REFERENCES pagos(id),
                recibido_en TEXT NOT NULL
            )
            """
        )
