"""Límites de profundidad y costo de las consultas GraphQL, y bloqueo de introspección."""
from graphql.language import (
    FieldNode,
    FragmentSpreadNode,
    FragmentDefinitionNode,
    InlineFragmentNode,
    OperationDefinitionNode,
)

MAX_DEPTH = 5  # niveles de campos anidados
MAX_FIELDS = 40  # campos totales (los alias cuentan: evita consultas gigantes)


class LimitError(Exception):
    pass


def analyze(document) -> None:
    """Rechaza la consulta apenas supera un límite (se llama después de validar el documento)."""
    fragments = {
        d.name.value: d for d in document.definitions if isinstance(d, FragmentDefinitionNode)
    }
    stats = {"fields": 0}

    def walk(selection_set, level: int) -> None:
        if level > MAX_DEPTH:
            raise LimitError("La consulta es demasiado profunda")
        for sel in selection_set.selections:
            if isinstance(sel, FieldNode):
                name = sel.name.value
                if name.startswith("__") and name != "__typename":
                    raise LimitError("La introspección está deshabilitada")
                stats["fields"] += 1
                if stats["fields"] > MAX_FIELDS:
                    raise LimitError("La consulta es demasiado costosa")
                if sel.selection_set:
                    walk(sel.selection_set, level + 1)
            elif isinstance(sel, InlineFragmentNode):
                walk(sel.selection_set, level)
            elif isinstance(sel, FragmentSpreadNode):
                walk(fragments[sel.name.value].selection_set, level)

    for definition in document.definitions:
        if isinstance(definition, OperationDefinitionNode):
            if definition.operation.value != "query":
                raise LimitError("Solo se permiten consultas")
            walk(definition.selection_set, 1)
