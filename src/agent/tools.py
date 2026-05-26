from __future__ import annotations

import re
import unicodedata

from src.graph.neo4j_client import Neo4jClient
from src.graph.schema_intro import graph_schema_summary

_WRITE_PATTERN = re.compile(
    r"\b(CREATE|MERGE|DELETE|SET|REMOVE|DROP|CALL)\b", re.IGNORECASE
)

# Entity labels that carry a human name and an `id` property.
_ENTITY_LABELS = ["Team", "Player", "Coach", "Stadium", "Referee"]
_FT_INDEX = "entity_name_ft"


def get_graph_schema() -> str:
    """Return the graph schema description for the agent."""
    return graph_schema_summary()


def _clean_word(word: str) -> str:
    """Lowercase, strip accents (NFKD) and keep only alphanumerics — mirrors how ids are
    normalised, so a user's word matches the stored id regardless of accents/punctuation."""
    decomposed = unicodedata.normalize("NFKD", word)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return "".join(ch for ch in no_accents.lower() if ch.isalnum())


def _query_tokens(name: str) -> list[str]:
    """Split a free-text name into cleaned tokens of length >= 2."""
    return [t for t in (_clean_word(w) for w in re.split(r"\s+", name.strip())) if len(t) >= 2]


def _lucene_query(tokens: list[str]) -> str:
    """Build a Lucene query: each token both fuzzy (~2, typos) and prefix (*, partials), OR-ed."""
    return " ".join(f"{t}~2 {t}*" for t in tokens)


def find_entity(name: str, label: str | None = None, limit: int = 5) -> dict:
    """Resolve a free-text entity name to its canonical graph id(s).

    Tolerant to accents, apostrophes, missing club suffixes, word order and typos. Tries the
    full-text index first (fast, fuzzy), then exact token-containment, then pure fuzzy ranking.
    All queries are parameterised — names are never interpolated into Cypher. Returns
    {"matches": [{"label", "id", "name", "score"}], "error": None}.
    """
    tokens = _query_tokens(name)
    if not tokens:
        return {"matches": [], "error": "name too short to search"}
    clean = "".join(tokens)
    params = {"labels": _ENTITY_LABELS, "label": label, "tokens": tokens, "clean": clean, "limit": limit}

    # Relevance = token coverage (how many query words appear in the id, order-independent)
    # blended with edit-distance similarity (forgives typos). Coverage dominates so a full
    # word match outranks a fuzzy partial; similarity breaks ties and rescues misspellings.
    score_expr = (
        "0.6 * (reduce(s = 0.0, t IN $tokens | s + CASE WHEN cid CONTAINS t THEN 1.0 ELSE 0.0 END) "
        "/ size($tokens)) + 0.4 * apoc.text.levenshteinSimilarity(cid, $clean)"
    )

    def _rank(rows: list[dict]) -> list[dict]:
        return sorted(rows, key=lambda r: r["score"], reverse=True)[:limit]

    # 1) Full-text index (Lucene): handles typos and multi-token / word-order queries at scale.
    ft = f"""
    CALL db.index.fulltext.queryNodes($index, $q) YIELD node
    WHERE ($label IS NULL OR $label IN labels(node)) AND any(l IN labels(node) WHERE l IN $labels)
    WITH node, apoc.text.clean(node.id) AS cid, [l IN labels(node) WHERE l IN $labels][0] AS lbl
    RETURN lbl AS label, node.id AS id, node.name AS name, {score_expr} AS score
    ORDER BY score DESC LIMIT $limit
    """
    matches: list[dict] = []
    try:
        with Neo4jClient() as client:
            matches = client.run_read(ft, index=_FT_INDEX, q=_lucene_query(tokens), **params)
    except Exception:
        matches = []  # index missing or APOC unavailable → fall through to scans

    # 2) Token-containment over cleaned ids: robust for suffixes/apostrophes/word order.
    if not matches:
        tc = f"""
        MATCH (n) WHERE ($label IS NULL OR $label IN labels(n)) AND any(l IN labels(n) WHERE l IN $labels)
        WITH n, apoc.text.clean(n.id) AS cid, [l IN labels(n) WHERE l IN $labels][0] AS lbl
        WHERE all(t IN $tokens WHERE cid CONTAINS t)
        RETURN lbl AS label, n.id AS id, n.name AS name, {score_expr} AS score
        ORDER BY score DESC LIMIT $limit
        """
        with Neo4jClient() as client:
            matches = client.run_read(tc, **params)

    # 3) Pure fuzzy ranking: last resort for typos that break token containment.
    if not matches:
        fz = """
        MATCH (n) WHERE ($label IS NULL OR $label IN labels(n)) AND any(l IN labels(n) WHERE l IN $labels)
        WITH n, apoc.text.clean(n.id) AS cid, [l IN labels(n) WHERE l IN $labels][0] AS lbl
        WITH lbl, n, apoc.text.levenshteinSimilarity(cid, $clean) AS score
        WHERE score >= 0.55
        RETURN lbl AS label, n.id AS id, n.name AS name, score
        ORDER BY score DESC LIMIT $limit
        """
        with Neo4jClient() as client:
            matches = client.run_read(fz, **params)

    return {"matches": _rank(matches), "error": None}


def validate_cypher(query: str, params: dict | None = None) -> dict:
    """Run EXPLAIN on a Cypher query to check syntax without executing it."""
    try:
        with Neo4jClient() as client:
            client.run_read(f"EXPLAIN {query}", **(params or {}))
        return {"ok": True, "error": None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def run_cypher(query: str, params: dict | None = None) -> dict:
    """Execute a read-only Cypher query (with optional parameters) and return rows.

    Values must be passed via ``params`` and referenced as ``$name`` in the query — never
    interpolated into the query text (safe against quoting/escaping and injection)."""
    match = _WRITE_PATTERN.search(query)
    if match:
        return {"rows": [], "error": f"read-only mode: {match.group(0).upper()} not allowed"}
    try:
        with Neo4jClient() as client:
            rows = client.run_read(query, **(params or {}))
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
            "name": "find_entity",
            "description": (
                "Resolves a free-text team/player/coach/stadium/referee name to its canonical "
                "graph id(s). Use this BEFORE filtering by any name: it is tolerant to accents, "
                "apostrophes, missing club suffixes (e.g. 'Cirera' → 'CIRERA, U.D. A'), different "
                "word order (e.g. 'Nayara Alfaro') and typos. Returns ranked candidates "
                "[{label, id, name, score}]. Use the returned id for exact matches in run_cypher."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "The name to resolve, as the user wrote it"},
                    "label": {
                        "type": "string",
                        "description": "Optional label filter: Team, Player, Coach, Stadium or Referee",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_cypher",
            "description": (
                "Validates the syntax of a Cypher query using EXPLAIN (does not execute, returns no rows). "
                "Always call this before running a new query to catch syntax errors. "
                "Pass the same params you will run with."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The Cypher query to validate, using $name placeholders"},
                    "params": {
                        "type": "object",
                        "description": "Query parameters referenced as $name in the query.",
                        "additionalProperties": True,
                    },
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
                "Pass every literal value (ids, names, numbers) via params as $name — never inline "
                "them into the query text. Returns {rows: [...], error: null} or {rows: [], error: 'message'}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The read-only Cypher query, using $name placeholders for values"},
                    "params": {
                        "type": "object",
                        "description": "Query parameters referenced as $name in the query (e.g. ids returned by find_entity).",
                        "additionalProperties": True,
                    },
                },
                "required": ["query"],
            },
        },
    },
]
