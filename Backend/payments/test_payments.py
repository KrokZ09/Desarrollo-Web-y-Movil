import hashlib
import hmac
import json
import os
import tempfile

# Se configura el entorno ANTES de importar la app
os.environ["PAYMENTS_DB"] = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["GW_PAYMENTS"] = "tok-gw-payments"
os.environ["PAYMENTS_ORDERS"] = "tok-payments-orders"
os.environ["PAYMENTS_WEBHOOK_SECRET"] = "secreto-de-prueba-del-proveedor"

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from db import get_conn  # noqa: E402

client = TestClient(main.app)
SECRET = os.environ["PAYMENTS_WEBHOOK_SECRET"]
ORDERS = {}
CALLS = []
MODE = {"fail": None}


def fake_orders(method, path):
    """Simula orders: sin red."""
    if MODE["fail"] == "down":
        raise HTTPException(503, "Servicio no disponible, intenta más tarde")
    order_id = int(path.strip("/").split("/")[2])
    if order_id not in ORDERS:
        raise HTTPException(404, "Pedido no encontrado")
    if path.endswith("mark-paid"):
        CALLS.append(order_id)
        if ORDERS[order_id]["estado"] == "ANULADO":
            raise HTTPException(409, "El pedido no admite pago en su estado actual")
        ORDERS[order_id]["estado"] = "PAGADO"
    return dict(ORDERS[order_id])


main.call_orders = fake_orders


def setup_function():
    MODE["fail"] = None
    CALLS.clear()


def pedido(order_id, cliente, total=16300, estado="PENDIENTE_PAGO"):
    ORDERS[order_id] = {"id": order_id, "clienteId": cliente, "estado": estado, "total": total}


def gw(user_id, role="cliente"):
    return {"X-Service-Token": "tok-gw-payments", "X-User-Id": str(user_id), "X-User-Role": role}


def pagar(order_id, user_id):
    return client.post(f"/orders/{order_id}/payments", headers=gw(user_id))


def aviso(body, firmar=True, firma=None):
    raw = json.dumps(body).encode()
    headers = {"X-Service-Token": "tok-gw-payments", "Content-Type": "application/json"}
    if firmar:
        headers["X-Signature"] = firma or hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return client.post("/payments/webhook", content=raw, headers=headers)


def estado_pago(order_id):
    with get_conn() as conn:
        rows = conn.execute("SELECT estado FROM pagos WHERE pedido_id = ? ORDER BY id", (order_id,)).fetchall()
    return [r["estado"] for r in rows]


def test_cliente_inicia_pago_de_su_pedido():
    pedido(1, cliente=7)
    r = pagar(1, 7)
    assert r.status_code == 201
    assert r.json()["estado"] == "PENDIENTE"
    with get_conn() as conn:
        assert conn.execute("SELECT monto FROM pagos WHERE pedido_id = 1").fetchone()["monto"] == 16300


def test_pedido_ajeno_es_403():
    pedido(2, cliente=7)
    assert pagar(2, 8).status_code == 403
    assert estado_pago(2) == []


def test_pedido_inexistente_es_404():
    assert pagar(999, 7).status_code == 404


def test_pedido_ya_pagado_es_409():
    pedido(3, cliente=7, estado="PAGADO")
    assert pagar(3, 7).status_code == 409


def test_admin_no_inicia_pagos():
    pedido(4, cliente=7)
    assert client.post("/orders/4/payments", headers=gw(1, "admin")).status_code == 403


def test_iniciar_dos_veces_reutiliza_el_pago_pendiente():
    pedido(5, cliente=7)
    assert pagar(5, 7).json()["paymentId"] == pagar(5, 7).json()["paymentId"]
    assert estado_pago(5) == ["PENDIENTE"]


def test_orders_caido_al_iniciar_pago_es_503():
    pedido(6, cliente=7)
    MODE["fail"] = "down"
    assert pagar(6, 7).status_code == 503


def test_aviso_sin_firma_es_401():
    pedido(10, cliente=7)
    pagar(10, 7)
    assert aviso({"eventId": "e10", "orderId": 10, "status": "PAID"}, firmar=False).status_code == 401
    assert ORDERS[10]["estado"] == "PENDIENTE_PAGO"


def test_aviso_con_firma_falsa_es_401():
    pedido(11, cliente=7)
    pagar(11, 7)
    r = aviso({"eventId": "e11", "orderId": 11, "status": "PAID"}, firma="0" * 64)
    assert r.status_code == 401
    assert ORDERS[11]["estado"] == "PENDIENTE_PAGO"


def test_aviso_sin_token_de_servicio_es_401():
    assert client.post("/payments/webhook", content=b"{}").status_code == 401


def test_aviso_valido_marca_el_pedido_como_pagado():
    pedido(12, cliente=7)
    pagar(12, 7)
    assert aviso({"eventId": "e12", "orderId": 12, "status": "PAID"}).status_code == 200
    assert ORDERS[12]["estado"] == "PAGADO"
    assert estado_pago(12) == ["APROBADO"]


def test_aviso_duplicado_no_se_procesa_dos_veces():
    pedido(13, cliente=7)
    pagar(13, 7)
    body = {"eventId": "e13", "orderId": 13, "status": "PAID"}
    assert aviso(body).status_code == 200
    segundo = aviso(body)
    assert segundo.status_code == 200
    assert segundo.json()["duplicate"] is True
    assert CALLS == [13]


def test_monto_alterado_no_paga_el_pedido():
    pedido(14, cliente=7)
    pagar(14, 7)
    r = aviso({"eventId": "e14", "orderId": 14, "status": "PAID", "amount": 1})
    assert r.status_code == 409
    assert ORDERS[14]["estado"] == "PENDIENTE_PAGO"


def test_orders_caido_en_el_aviso_permite_reintento():
    pedido(15, cliente=7)
    pagar(15, 7)
    body = {"eventId": "e15", "orderId": 15, "status": "PAID"}
    MODE["fail"] = "down"
    assert aviso(body).status_code == 503
    MODE["fail"] = None
    assert aviso(body).status_code == 200  # el evento no quedó registrado, así que se procesa
    assert ORDERS[15]["estado"] == "PAGADO"


def test_pago_rechazado_permite_un_nuevo_intento():
    pedido(16, cliente=7)
    primero = pagar(16, 7).json()["paymentId"]
    assert aviso({"eventId": "e16", "orderId": 16, "status": "FAILED"}).status_code == 200
    assert estado_pago(16) == ["RECHAZADO"]
    segundo = pagar(16, 7).json()["paymentId"]
    assert segundo != primero


def test_pago_de_pedido_anulado_va_a_revision_manual():
    pedido(17, cliente=7)
    pagar(17, 7)
    ORDERS[17]["estado"] = "ANULADO"
    assert aviso({"eventId": "e17", "orderId": 17, "status": "PAID"}).status_code == 200
    assert estado_pago(17) == ["REVISION_MANUAL"]


def test_aviso_con_estado_invalido_es_400():
    pedido(18, cliente=7)
    pagar(18, 7)
    assert aviso({"eventId": "e18", "orderId": 18, "status": "QUIZAS"}).status_code == 400


def test_aviso_de_pedido_sin_pago_pendiente_es_404():
    pedido(19, cliente=7)
    assert aviso({"eventId": "e19", "orderId": 19, "status": "PAID"}).status_code == 404
