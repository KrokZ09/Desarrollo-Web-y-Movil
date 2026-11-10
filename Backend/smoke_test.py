"""Prueba de extremo a extremo contra los servicios REALES (no simulados).

Uso (con run_all.py corriendo en otra terminal, desde la carpeta Backend):
    python smoke_test.py
Deja el resultado en smoke_results.txt (no contiene tokens ni claves).
Nota: el gateway limita registro/login a 10 por minuto; si repites la prueba,
espera un minuto o reinicia run_all.py.
"""
import hashlib
import hmac
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).parent
GATEWAY = "http://127.0.0.1:8000"
API = f"{GATEWAY}/api/v1"
PRIVATE = {"auth": 8001, "clients": 8002, "inventory": 8003, "orders": 8004, "payments": 8005, "graphql": 8006}
RESULTS = []


def read_env(service: str) -> dict:
    out = {}
    for line in (ROOT / service / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip()
    return out


def check(name: str, ok: bool, detail: str = ""):
    RESULTS.append((name, ok, detail))
    print(f"[{'OK' if ok else 'FALLA'}] {name}" + (f"  ({detail})" if detail else ""))


def call(method, path, token=None, json_body=None, content=None, headers=None, base=API):
    h = dict(headers or {})
    if token:
        h["Authorization"] = f"Bearer {token}"
    return httpx.request(method, f"{base}{path}", json=json_body, content=content, headers=h, timeout=10.0)


def register_and_login(prefix: str):
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    password = "ClaveDePrueba123"
    r = call("POST", "/auth/register", json_body={"nombre": prefix, "email": email, "password": password})
    login = call("POST", "/auth/login", json_body={"email": email, "password": password})
    return email, password, r, login


def sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


def main():
    admin_env, pay_env = read_env("auth"), read_env("payments")
    try:
        httpx.get(f"{GATEWAY}/health", timeout=3.0)
    except httpx.HTTPError:
        print("El gateway no responde. Inicia primero: python run_all.py")
        sys.exit(2)

    # ---- Catálogo público y separación pública/privada ----
    r = call("GET", "/products")
    catalog = r.json() if r.status_code == 200 else []
    check("Catálogo anónimo por el gateway", r.status_code == 200 and len(catalog) >= 4, f"{len(catalog)} productos")
    check("El catálogo público no expone stock", all("stock" not in p for p in catalog))
    for name, port, method, path in [
        ("inventory", 8003, "GET", "/products"),
        ("orders", 8004, "GET", "/orders"),
        ("clients", 8002, "GET", "/clients/me"),
        ("payments", 8005, "POST", "/payments/webhook"),
        ("graphql", 8006, "POST", "/graphql"),
        ("auth", 8001, "POST", "/login"),
    ]:
        d = httpx.request(method, f"http://127.0.0.1:{port}{path}", timeout=5.0)
        check(f"Acceso directo a {name} sin credencial de servicio", d.status_code == 401, f"HTTP {d.status_code}")
    r = call("GET", "/orders", token=None)
    check("Operación protegida sin sesión", r.status_code == 401, f"HTTP {r.status_code}")
    r = call("GET", "/orders", token="token.falso.xxx")
    check("Token falso rechazado", r.status_code == 401, f"HTTP {r.status_code}")
    r1, r2 = call("GET", "/internal/stock/reserve"), call("GET", "/internal/orders/1")
    check("Rutas internas no publicadas en el gateway", r1.status_code == 404 and r2.status_code == 404)

    # ---- Registro y autenticación ----
    email_a, pass_a, reg_a, login_a = register_and_login("cliente-a")
    email_b, pass_b, reg_b, login_b = register_and_login("cliente-b")
    check("Registro de clientes", reg_a.status_code == 201 and reg_b.status_code == 201, f"HTTP {reg_a.status_code}/{reg_b.status_code}")
    check("El registro no devuelve la contraseña", "password" not in reg_a.text.lower())
    dup = call("POST", "/auth/register", json_body={"nombre": "x", "email": email_a, "password": pass_a})
    check("Correo duplicado rechazado", dup.status_code == 409, f"HTTP {dup.status_code}")
    bad = call("POST", "/auth/login", json_body={"email": email_a, "password": "incorrecta123"})
    check("Login con clave incorrecta", bad.status_code == 401, f"HTTP {bad.status_code}")
    tok_a, tok_b = login_a.json().get("accessToken"), login_b.json().get("accessToken")
    check("Login correcto entrega token", bool(tok_a) and bool(tok_b))
    perfil = call("GET", "/clients/me", token=tok_a)
    check("Cliente ve su perfil", perfil.status_code == 200 and perfil.json().get("email") == email_a)
    adm = call("POST", "/auth/login", json_body={"email": admin_env["ADMIN_EMAIL"], "password": admin_env["ADMIN_PASSWORD"]})
    tok_admin = adm.json().get("accessToken")
    check("Login de administración", adm.status_code == 200 and bool(tok_admin))

    # ---- Pedidos y propiedad ----
    p1, p2 = catalog[0], catalog[1]
    body = {
        "items": [{"productId": p1["id"], "cantidad": 2}, {"productId": p2["id"], "cantidad": 1}],
        "direccionEntrega": "Calle Falsa 123, Paine",
        "total": 1,
        "estado": "PAGADO",
    }
    r = call("POST", "/orders", token=tok_a, json_body=body)
    order = r.json() if r.status_code == 201 else {}
    expected = p1["precio"] * 2 + p2["precio"]
    check("Pedido creado con total calculado por el servidor", r.status_code == 201 and order.get("total") == expected, f"total {order.get('total')} esperado {expected}")
    check("El estado enviado por el navegador se ignora", order.get("estado") == "PENDIENTE_PAGO")
    oid = order.get("id")
    r = call("GET", f"/orders/{oid}", token=tok_b)
    check("Cliente B no ve el pedido de A", r.status_code == 403 and "Calle Falsa" not in r.text, f"HTTP {r.status_code}")
    check("Cliente A ve su pedido", call("GET", f"/orders/{oid}", token=tok_a).status_code == 200)
    check("Listado de B no incluye pedidos de A", call("GET", "/orders", token=tok_b).json() == [])
    r = call("PUT", f"/products/{p1['id']}", token=tok_a, json_body={"nombre": "x", "descripcion": "x", "precio": 1, "disponible": True})
    check("Cliente no puede editar productos", r.status_code == 403, f"HTTP {r.status_code}")
    check("Cliente no puede listar todos los pedidos", call("GET", "/admin/orders", token=tok_a).status_code == 403)
    r = call("GET", "/admin/orders", token=tok_admin)
    check("Admin lista todos los pedidos", r.status_code == 200 and any(o["id"] == oid for o in r.json()))
    direct = httpx.get("http://127.0.0.1:8004/orders", headers={"Authorization": f"Bearer {tok_a}"}, timeout=5.0)
    check("El token del usuario no sirve contra el servicio directo", direct.status_code == 401, f"HTTP {direct.status_code}")

    # ---- Pagos ----
    secret = pay_env["PAYMENTS_WEBHOOK_SECRET"]

    def aviso(event_id, status="PAID", amount=None, signature=None, order_id=None):
        data = {"eventId": event_id, "orderId": order_id or oid, "status": status}
        if amount is not None:
            data["amount"] = amount
        raw = json.dumps(data, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if signature != "none":
            headers["X-Signature"] = signature or sign(secret, raw)
        return call("POST", "/payments/webhook", content=raw, headers=headers)

    estado = lambda: call("GET", f"/orders/{oid}", token=tok_a).json().get("estado")
    r = aviso("evt-" + uuid.uuid4().hex[:6], signature="none")
    check("Aviso de pago sin firma rechazado", r.status_code == 401 and estado() == "PENDIENTE_PAGO", f"HTTP {r.status_code}")
    r = aviso("evt-" + uuid.uuid4().hex[:6], signature="0" * 64)
    check("Aviso de pago con firma falsa rechazado", r.status_code == 401 and estado() == "PENDIENTE_PAGO")
    r = call("POST", f"/orders/{oid}/payments", token=tok_a)
    check("Cliente inicia el pago de su pedido", r.status_code == 201, f"HTTP {r.status_code}")
    check("Cliente B no puede pagar el pedido de A", call("POST", f"/orders/{oid}/payments", token=tok_b).status_code == 403)
    r = aviso("evt-" + uuid.uuid4().hex[:6], amount=1)
    check("Aviso firmado con monto alterado no paga el pedido", r.status_code == 409 and estado() == "PENDIENTE_PAGO", f"HTTP {r.status_code}")
    event = "evt-" + uuid.uuid4().hex[:6]
    r = aviso(event)
    check("Aviso firmado válido marca el pedido como PAGADO", r.status_code == 200 and estado() == "PAGADO", f"HTTP {r.status_code}")
    r = aviso(event)
    check("Aviso duplicado no se procesa dos veces", r.status_code == 200 and r.json().get("duplicate") is True)
    check("No se puede anular un pedido pagado", call("DELETE", f"/orders/{oid}", token=tok_a).status_code == 409)

    # ---- GraphQL ----
    def gql(query, token):
        return call("POST", "/graphql", token=token, json_body={"query": query})

    r = gql(f"query {{ resumenPedido(id: {oid}) {{ estado items {{ nombre producto {{ descripcion }} }} }} }}", tok_a)
    data = (r.json().get("data") or {}).get("resumenPedido") or {}
    items = data.get("items") or []
    check("GraphQL combina orders (estado) con inventory (descripción)", data.get("estado") == "PAGADO" and bool(items) and bool((items[0].get("producto") or {}).get("descripcion")))
    r = gql(f"query {{ resumenPedido(id: {oid}) {{ estado direccionEntrega }} }}", tok_a)
    check("GraphQL: el cliente no obtiene la dirección", (r.json()["data"]["resumenPedido"] or {}).get("direccionEntrega") is None and "Calle Falsa" not in r.text)
    r = gql(f"query {{ resumenPedido(id: {oid}) {{ direccionEntrega }} }}", tok_admin)
    check("GraphQL: el admin sí obtiene la dirección", (r.json()["data"]["resumenPedido"] or {}).get("direccionEntrega") == "Calle Falsa 123, Paine")
    r = gql(f"query {{ resumenPedido(id: {oid}) {{ estado }} }}", tok_b)
    check("GraphQL: pedido ajeno no se entrega", r.json()["data"]["resumenPedido"] is None and "Calle Falsa" not in r.text)
    check("GraphQL: introspección deshabilitada", gql("query { __schema { types { name } } }", tok_a).status_code == 400)
    check("GraphQL sin sesión", call("POST", "/graphql", json_body={"query": "{ __typename }"}).status_code == 401)

    # ---- Stock: reserva y recuperación ----
    p4 = catalog[3]
    call("PUT", f"/products/{p4['id']}/stock", token=tok_admin, json_body={"stock": 1})
    one = {"items": [{"productId": p4["id"], "cantidad": 1}], "direccionEntrega": "Calle Falsa 123, Paine"}
    first = call("POST", "/orders", token=tok_a, json_body=one)
    second = call("POST", "/orders", token=tok_a, json_body=one)
    check("Sin stock el segundo pedido es rechazado", first.status_code == 201 and second.status_code == 409, f"HTTP {first.status_code}/{second.status_code}")
    anulado = call("DELETE", f"/orders/{first.json().get('id')}", token=tok_a)
    check("Anular conserva el registro", anulado.status_code == 200 and anulado.json().get("estado") == "ANULADO")
    third = call("POST", "/orders", token=tok_a, json_body=one)
    check("Anular devuelve el stock", third.status_code == 201, f"HTTP {third.status_code}")

    # ---- Resumen ----
    fallas = [n for n, ok, _ in RESULTS if not ok]
    lines = [f"Prueba de extremo a extremo - {datetime.now().isoformat(timespec='seconds')}", ""]
    lines += [f"[{'OK' if ok else 'FALLA'}] {n}" + (f" ({d})" if d else "") for n, ok, d in RESULTS]
    lines += ["", f"Total: {len(RESULTS)} comprobaciones, {len(RESULTS) - len(fallas)} correctas, {len(fallas)} con falla"]
    (ROOT / "smoke_results.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"\n{len(RESULTS) - len(fallas)}/{len(RESULTS)} correctas. Resultado guardado en smoke_results.txt")
    sys.exit(1 if fallas else 0)


if __name__ == "__main__":
    main()
