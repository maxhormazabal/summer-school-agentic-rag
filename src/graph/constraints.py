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


def apply() -> None:
    """Apply uniqueness constraints (idempotent via IF NOT EXISTS)."""
    with Neo4jClient() as client:
        for stmt in _CONSTRAINTS:
            client.run_write(stmt)
    console.print("[green]Constraints applied.[/green]")
