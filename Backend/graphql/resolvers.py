import asyncio
import os
from dataclasses import dataclass, field

import httpx
from graphql import GraphQLError, default_field_resolver

from secrets_provider import get_secret

ORDERS_URL = os.environ.get("ORDERS_URL", "http://127.0.0.1:8004")
INVENTORY_URL = os.environ.get("INVENTORY_URL", "http://127.0.0.1:8003")
ORDERS_TOKEN = get_secret("GRAPHQL_ORDERS")  # credencial de solo lectura hacia orders
INVENTORY_TOKEN = get_secret("GRAPHQL_INVENTORY")  # credencial de solo lectura hacia inventory
PUBLIC_PRODUCT_FIELDS = ("id", "nombre", "descripcion", "precio", "disponible")


async def http_get(url: str, headers: dict):
    """GET interno con plazo de 3 s (se separa para poder probar sin red)."""
    async with httpx.AsyncClient(timeout=3.0) as client:
        return await client.get(url, headers=headers)


class CatalogLoader:
    """Una sola llamada a inventory por consulta, sin importar cuántos ítems tenga el pedido."""

    def __init__(self):
        self._task = None
        self.calls = 0

    async def load(self) -> dict:
        if self._task is None:
            self.calls += 1
            self._task = asyncio.ensure_future(self._fetch())
        return await self._task

    async def _fetch(self) -> dict:
        try:
            r = await http_get(f"{INVENTORY_URL}/products", {"X-Service-Token": INVENTORY_TOKEN})
        except httpx.HTTPError:
            raise GraphQLError("El catálogo no está disponible")
        if r.status_code != 200:
            raise GraphQLError("El catálogo no está disponible")
        return {p["id"]: {k: p[k] for k in PUBLIC_PRODUCT_FIELDS} for p in r.json()}


@dataclass
class Context:
    user_id: str  # identidad verificada por el API Gateway
    role: str
    catalog: CatalogLoader = field(default_factory=CatalogLoader)


async def resolve_resumen_pedido(source, info, id):
    ctx = info.context
    headers = {"X-Service-Token": ORDERS_TOKEN, "X-User-Id": ctx.user_id, "X-User-Role": ctx.role}
    try:
        # orders decide si el pedido es del usuario: la propiedad no se vuelve a implementar aquí
        r = await http_get(f"{ORDERS_URL}/orders/{id}", headers)
    except httpx.HTTPError:
        raise GraphQLError("El servicio de pedidos no está disponible")
    if r.status_code == 403:
        raise GraphQLError("No tienes acceso a este pedido")
    if r.status_code == 404:
        raise GraphQLError("Pedido no encontrado")
    if r.status_code != 200:
        raise GraphQLError("El servicio de pedidos no está disponible")
    order = r.json()
    if ctx.role != "admin":
        order.pop("direccionEntrega", None)  # el dato restringido ni siquiera avanza
    return order


async def resolve_producto(item, info):
    catalog = await info.context.catalog.load()
    return catalog.get(item["productId"])


def resolve_direccion(order, info):
    if info.context.role != "admin":
        raise GraphQLError("No autorizado para el campo direccionEntrega")
    return order.get("direccionEntrega")


RESOLVERS = {
    ("Query", "resumenPedido"): resolve_resumen_pedido,
    ("ItemResumen", "producto"): resolve_producto,
    ("ResumenPedido", "direccionEntrega"): resolve_direccion,
}


def resolver(source, info, **args):
    fn = RESOLVERS.get((info.parent_type.name, info.field_name))
    if fn:
        return fn(source, info, **args)
    return default_field_resolver(source, info, **args)
