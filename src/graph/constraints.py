from src.graph.neo4j_client import Neo4jClient
from src.common.logging import console

_CONSTRAINTS = [
    "CREATE CONSTRAINT match_id   IF NOT EXISTS FOR (m:Match)   REQUIRE m.id IS UNIQUE",
    "CREATE CONSTRAINT team_id    IF NOT EXISTS FOR (t:Team)    REQUIRE t.id IS UNIQUE",
    "CREATE CONSTRAINT player_id  IF NOT EXISTS FOR (p:Player)  REQUIRE p.id IS UNIQUE",
    "CREATE CONSTRAINT coach_id   IF NOT EXISTS FOR (c:Coach)   REQUIRE c.id IS UNIQUE",
    "CREATE CONSTRAINT stadium_id IF NOT EXISTS FOR (s:Stadium) REQUIRE s.id IS UNIQUE",
    "CREATE CONSTRAINT referee_id IF NOT EXISTS FOR (r:Referee) REQUIRE r.id IS UNIQUE",
]

# Full-text (Lucene) index over entity ids, powering fuzzy name resolution in
# agent.tools.find_entity (tolerant to typos, word order and partial names).
_FULLTEXT_INDEX = (
    "CREATE FULLTEXT INDEX entity_name_ft IF NOT EXISTS "
    "FOR (n:Team|Player|Coach|Stadium|Referee) ON EACH [n.id]"
)


def apply() -> None:
    """Apply uniqueness constraints and the entity-name full-text index (idempotent)."""
    with Neo4jClient() as client:
        for stmt in _CONSTRAINTS:
            client.run_write(stmt)
        client.run_write(_FULLTEXT_INDEX)
    console.print("[green]Constraints + search index applied.[/green]")
