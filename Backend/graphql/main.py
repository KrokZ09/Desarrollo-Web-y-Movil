import asyncio
import logging
import secrets
from inspect import isawaitable
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from graphql import GraphQLError, build_schema, execute, parse, validate
from graphql.error import GraphQLSyntaxError

import limits
import resolvers
from secrets_provider import get_secret

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("graphql")

app = FastAPI(title="graphql-gateway")

GATEWAY_TOKEN = get_secret("GW_GRAPHQL")  # solo el API Gateway puede llamar a este servicio
schema = build_schema(Path(__file__).with_name("schema.graphql").read_text(encoding="utf-8"))
MAX_QUERY_CHARS = 2000
EXECUTION_TIMEOUT = 8.0


def gateway_only(x_service_token: Optional[str] = Header(None)):
    if not x_service_token or not secrets.compare_digest(
        x_service_token.encode(), GATEWAY_TOKEN.encode()
    ):
        raise HTTPException(401, "No autorizado")


def bad_request(message: str):
    return JSONResponse(status_code=400, content={"errors": [{"message": message}]})


def format_errors(errors, correlation_id) -> list:
    """Errores propios y de validación se muestran; los inesperados se ocultan."""
    out = []
    for e in errors:
        original = e.original_error
        if original is not None and not isinstance(original, GraphQLError):
            log.error("%s error inesperado: %s", correlation_id, type(original).__name__)
            out.append({"message": "Error interno", "path": e.path})
        else:
            out.append({"message": e.message, "path": e.path})
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/graphql", dependencies=[Depends(gateway_only)])
async def graphql_endpoint(
    request: Request,
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    x_correlation_id: Optional[str] = Header(None),
):
    # Identidad verificada por el gateway (solo se confía porque la ruta exige su credencial)
    if not x_user_id or not x_user_id.isdigit() or x_user_role not in ("cliente", "admin"):
        raise HTTPException(401, "No autorizado")
    try:
        body = await request.json()
    except Exception:
        return bad_request("Cuerpo inválido")
    if not isinstance(body, dict):
        return bad_request("Cuerpo inválido")
    query, variables, op_name = body.get("query"), body.get("variables"), body.get("operationName")
    if not isinstance(query, str) or len(query) > MAX_QUERY_CHARS:
        return bad_request("Consulta inválida o demasiado larga")
    if variables is not None and not isinstance(variables, dict):
        return bad_request("Variables inválidas")
    if op_name is not None and not isinstance(op_name, str):
        return bad_request("Nombre de operación inválido")

    try:
        document = parse(query)
    except GraphQLSyntaxError:
        return bad_request("La consulta tiene errores de sintaxis")
    errors = validate(schema, document)  # también rechaza mutaciones: el schema no las define
    if errors:
        return bad_request("; ".join(e.message for e in errors))
    try:
        limits.analyze(document)  # profundidad, costo e introspección
    except limits.LimitError as exc:
        return bad_request(str(exc))

    ctx = resolvers.Context(user_id=x_user_id, role=x_user_role)
    try:
        result = execute(
            schema,
            document,
            context_value=ctx,
            variable_values=variables,
            operation_name=op_name,
            field_resolver=resolvers.resolver,
        )
        if isawaitable(result):
            result = await asyncio.wait_for(result, EXECUTION_TIMEOUT)
    except asyncio.TimeoutError:
        return JSONResponse(status_code=504, content={"errors": [{"message": "Tiempo de espera agotado"}]})

    out = {"data": result.data}
    if result.errors:
        out["errors"] = format_errors(result.errors, x_correlation_id)
    log.info("%s consulta ejecutada (usuario %s, errores: %s)", x_correlation_id, x_user_id, len(result.errors or []))
    return out
