import logging
import os
import uuid
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from policies import AuthenticationPolicy, AuthorizationPolicy, RateLimitPolicy
from routes import match
from secrets_provider import get_secret

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("gateway")

app = FastAPI(title="api-gateway")

MAX_BODY = 64 * 1024  # 64 KB
TIMEOUT = 5.0  # plazo máximo por llamada interna (segundos)
LIMITS = {"auth": 10, "default": 120}  # solicitudes por minuto y por IP


@dataclass(frozen=True)
class ServiceTarget:
    name: str
    base_url: str
    token: str  # credencial de servicio del gateway para ese destino


# Una credencial distinta por destino, leída por referencia (nunca escrita en el código)
TARGETS = {
    "auth": ServiceTarget("auth", os.environ.get("AUTH_URL", "http://127.0.0.1:8001"), get_secret("GW_AUTH")),
    "clients": ServiceTarget("clients", os.environ.get("CLIENTS_URL", "http://127.0.0.1:8002"), get_secret("GW_CLIENTS")),
    "inventory": ServiceTarget("inventory", os.environ.get("INVENTORY_URL", "http://127.0.0.1:8003"), get_secret("GW_INVENTORY")),
    "orders": ServiceTarget("orders", os.environ.get("ORDERS_URL", "http://127.0.0.1:8004"), get_secret("GW_ORDERS")),
    "payments": ServiceTarget("payments", os.environ.get("PAYMENTS_URL", "http://127.0.0.1:8005"), get_secret("GW_PAYMENTS")),
    "graphql": ServiceTarget("graphql", os.environ.get("GRAPHQL_URL", "http://127.0.0.1:8006"), get_secret("GW_GRAPHQL")),
}

authentication = AuthenticationPolicy(get_secret("JWT_SIGNING"))
authorization = AuthorizationPolicy()
limiter = RateLimitPolicy()


async def forward(method, url, headers, content, params):
    """Llamada HTTP al servicio interno (se separa para poder probar sin red)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.request(method, url, headers=headers, content=content, params=params)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def gateway(request: Request, full_path: str):
    path = "/" + full_path
    cid = uuid.uuid4().hex[:16]  # identificador de correlación para los logs

    def reply(status: int, detail: str):
        log.info("%s %s %s -> %s", cid, request.method, path, status)
        return JSONResponse(status_code=status, content={"detail": detail}, headers={"X-Correlation-Id": cid})

    route, path_params = match(request.method, path)
    if not route:
        return reply(404, "Ruta no encontrada")

    ip = request.client.host if request.client else "desconocido"
    if not limiter.allow(f"{route.bucket}:{ip}", LIMITS[route.bucket]):
        return reply(429, "Demasiadas solicitudes")

    identity = None
    if route.access == "auth":
        identity = authentication.verify(request.headers.get("authorization"))
        if identity is None:
            return reply(401, "No autorizado")
        if not authorization.check(route, identity[1]):
            return reply(403, "No tienes permiso para esta operación")

    body = await request.body()
    if len(body) > MAX_BODY:
        return reply(413, "Cuerpo demasiado grande")

    # Se construyen cabeceras NUEVAS: las de identidad que mande el navegador se descartan
    target = TARGETS[route.service]
    headers = {"X-Correlation-Id": cid, "X-Service-Token": target.token}
    if request.headers.get("content-type"):
        headers["Content-Type"] = request.headers["content-type"]
    if identity:
        headers["X-User-Id"], headers["X-User-Role"] = identity
    if route.access == "signed" and request.headers.get("x-signature"):
        headers["X-Signature"] = request.headers["x-signature"]  # lo verifica payments

    url = target.base_url + route.internal.format(**path_params)
    try:
        resp = await forward(
            request.method, url, headers, body, list(request.query_params.multi_items())
        )
    except httpx.TimeoutException:
        return reply(504, "El servicio tardó demasiado en responder")
    except httpx.HTTPError:
        return reply(503, "Servicio no disponible, intenta más tarde")

    log.info(
    "%s DEBUG service=%s access=%s upstream_status=%s",
    cid,
    route.service,
    route.access,
    resp.status_code
    )
    
    
    status = resp.status_code
    if status == 401 and route.service != "auth":
        if route.access != "signed":
            status = 502


    user = identity[0] if identity else "-"
    log.info("%s %s %s %s -> %s (usuario %s)", cid, route.id, request.method, path, status, user)
    return Response(
        content=resp.content,
        status_code=status,
        media_type=resp.headers.get("content-type", "application/json"),
        headers={"X-Correlation-Id": cid},
    )
