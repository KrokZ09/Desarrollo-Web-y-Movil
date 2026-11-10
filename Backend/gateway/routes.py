"""Lista explícita de rutas del gateway. Lo que no está aquí se rechaza con 404."""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class RouteDefinition:
    id: str  # ID de servicio del README (S01...)
    method: str
    pattern: str  # ruta externa; {id} acepta solo dígitos
    access: str  # "anon" (sin sesión), "auth" (token del usuario) o "signed" (firma del proveedor)
    roles: tuple  # roles permitidos cuando access == "auth"
    service: str  # sistema de destino
    internal: str  # ruta interna de destino
    bucket: str = "default"  # grupo para el límite de solicitudes


CLIENTE = ("cliente",)
ADMIN = ("admin",)
AMBOS = ("cliente", "admin")

ROUTES = [
    RouteDefinition("S01", "GET", "/api/v1/products", "anon", (), "inventory", "/products"),
    RouteDefinition("S02", "GET", "/api/v1/products/{id}", "anon", (), "inventory", "/products/{id}"),
    RouteDefinition("S03", "POST", "/api/v1/auth/register", "anon", (), "auth", "/register", "auth"),
    RouteDefinition("S04", "POST", "/api/v1/auth/login", "anon", (), "auth", "/login", "auth"),
    RouteDefinition("S05", "GET", "/api/v1/clients/me", "auth", CLIENTE, "clients", "/clients/me"),
    RouteDefinition("S06", "PUT", "/api/v1/clients/me", "auth", CLIENTE, "clients", "/clients/me"),
    RouteDefinition("S07", "POST", "/api/v1/orders", "auth", CLIENTE, "orders", "/orders"),
    RouteDefinition("S08", "GET", "/api/v1/orders", "auth", CLIENTE, "orders", "/orders"),
    RouteDefinition("S09", "GET", "/api/v1/orders/{id}", "auth", AMBOS, "orders", "/orders/{id}"),
    RouteDefinition("S10", "DELETE", "/api/v1/orders/{id}", "auth", CLIENTE, "orders", "/orders/{id}"),
    RouteDefinition("S11", "POST", "/api/v1/orders/{id}/payments", "auth", CLIENTE, "payments", "/orders/{id}/payments"),
    RouteDefinition("S12", "POST", "/api/v1/payments/webhook", "signed", (), "payments", "/payments/webhook"),
    RouteDefinition("S13", "POST", "/api/v1/products", "auth", ADMIN, "inventory", "/products"),
    RouteDefinition("S14", "PUT", "/api/v1/products/{id}", "auth", ADMIN, "inventory", "/products/{id}"),
    RouteDefinition("S15", "PUT", "/api/v1/products/{id}/stock", "auth", ADMIN, "inventory", "/products/{id}/stock"),
    RouteDefinition("S16", "GET", "/api/v1/admin/orders", "auth", ADMIN, "orders", "/admin/orders"),
    RouteDefinition("S17", "PUT", "/api/v1/orders/{id}/status", "auth", ADMIN, "orders", "/orders/{id}/status"),
    RouteDefinition("G01", "POST", "/api/v1/graphql", "auth", AMBOS, "graphql", "/graphql"),
]

_COMPILED = [
    (re.compile(r.pattern.replace("{id}", r"(?P<id>\d{1,12})")), r) for r in ROUTES
]


def match(method: str, path: str):
    """Devuelve (ruta, parámetros) o (None, None) si no está permitida."""
    for regex, route in _COMPILED:
        if route.method == method:
            m = regex.fullmatch(path)
            if m:
                return route, m.groupdict()
    return None, None
