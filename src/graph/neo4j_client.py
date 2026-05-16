from __future__ import annotations

import os
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


def _env_get(key: str) -> str | None:
    """Return env var value (after loading .env) or None."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    return os.environ.get(key) or None


class Neo4jClient:
    def __init__(self) -> None:
        from src.common.config import get_secret
        # AuraDB exports NEO4J_USERNAME; fall back to NEO4J_USER for other envs
        user = _env_get("NEO4J_USERNAME") or get_secret("NEO4J_USER")
        self._database = _env_get("NEO4J_DATABASE")
        self._driver = GraphDatabase.driver(
            get_secret("NEO4J_URI"),
            auth=(user, get_secret("NEO4J_PASSWORD")),
            connection_timeout=15,
        )

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self._driver.close()

    def _session(self):
        kwargs = {}
        if self._database:
            kwargs["database"] = self._database
        return self._driver.session(**kwargs)

    def run_read(self, cypher: str, **params: Any) -> list[dict]:
        with self._session() as session:
            result = session.run(cypher, **params)
            return [_serialize(dict(record)) for record in result]

    def run_write(self, cypher: str, **params: Any) -> list[dict]:
        with self._session() as session:
            result = session.run(cypher, **params)
            return [_serialize(dict(record)) for record in result]
