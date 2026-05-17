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
                "Returns the full Neo4J graph schema: labels, relationship types, "
                "properties and Cypher examples. Call this tool at the start of each "
                "conversation to understand the graph structure."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_cypher",
            "description": (
                "Validates the syntax of a Cypher query using EXPLAIN (does not execute, returns no rows). "
                "Always call this before running a new query to catch syntax errors."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The Cypher query to validate"}
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
                "Executes a read-only Cypher query against the Neo4J graph and returns the rows. "
                "Only read queries are allowed (MATCH, RETURN, WITH, WHERE, etc.). "
                "Returns {rows: [...], error: null} or {rows: [], error: 'message'}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The read-only Cypher query to execute"}
                },
                "required": ["query"],
            },
        },
    },
]
