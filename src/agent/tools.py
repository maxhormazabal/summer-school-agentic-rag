from __future__ import annotations

import re

from src.graph.neo4j_client import Neo4jClient
from src.graph.schema_intro import graph_schema_summary

_WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL)\b", re.IGNORECASE
)


def get_graph_schema() -> str:
    """Return the graph schema description for the agent."""
    return graph_schema_summary()


def validate_cypher(query: str) -> dict:
    """Run EXPLAIN on a Cypher query to check syntax without executing it."""
    try:
        with Neo4jClient() as client:
            client.run_read(f"EXPLAIN {query}")
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_cypher(query: str) -> dict:
    """Execute a read-only Cypher query and return rows."""
    match = _WRITE_PATTERN.search(query)
    if match:
        return {"rows": [], "error": f"read-only mode: {match.group(0).upper()} not allowed"}
    try:
        with Neo4jClient() as client:
            rows = client.run_read(query)
        return {"rows": rows, "error": None}
    except Exception as exc:
        return {"rows": [], "error": str(exc)}


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "get_graph_schema",
            "description": (
                "Devuelve el esquema completo del grafo Neo4J: labels, tipos de relación, "
                "propiedades y ejemplos de Cypher. Llama a esta herramienta al inicio de cada "
                "conversación para entender la estructura del grafo."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_cypher",
            "description": (
                "Valida la sintaxis de una query Cypher usando EXPLAIN (no ejecuta, no devuelve filas). "
                "Úsala siempre antes de ejecutar una query nueva para detectar errores de sintaxis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La query Cypher a validar"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_cypher",
            "description": (
                "Ejecuta una query Cypher de lectura contra el grafo Neo4J y devuelve las filas. "
                "Solo se permiten queries de lectura (MATCH, RETURN, WITH, WHERE, etc.). "
                "Devuelve {rows: [...], error: null} o {rows: [], error: 'mensaje'}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "La query Cypher de lectura a ejecutar"}
                },
                "required": ["query"],
            },
        },
    },
]
