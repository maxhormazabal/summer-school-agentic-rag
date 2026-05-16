from __future__ import annotations

from typing import Any

from neo4j import GraphDatabase, graph


def _serialize(value: Any) -> Any:
    """Recursively convert Neo4j Node/Relationship/Path to plain dicts."""
    if isinstance(value, (graph.Node, graph.Relationship)):
        return dict(value)
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


class Neo4jClient:
    def __init__(self) -> None:
        from src.common.config import get_secret
        self._driver = GraphDatabase.driver(
            get_secret("NEO4J_URI"),
            auth=(get_secret("NEO4J_USER"), get_secret("NEO4J_PASSWORD")),
            connection_timeout=15,
        )

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self._driver.close()

    def run_read(self, cypher: str, **params: Any) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [_serialize(dict(record)) for record in result]

    def run_write(self, cypher: str, **params: Any) -> list[dict]:
        with self._driver.session() as session:
            result = session.run(cypher, **params)
            return [_serialize(dict(record)) for record in result]
