from __future__ import annotations

from src.graph.neo4j_client import Neo4jClient

_ONTOLOGY_PROSE = """\
La base de datos contiene información sobre partidos de fútbol de la FCF (Federació Catalana de Futbol).

Nodos y propiedades principales:
- Match: id (string único), journey (int), competition, status, score_home (int), score_away (int)
- Team: id (nombre normalizado), name
- Player: id (nombre normalizado), name
- Coach: id (nombre normalizado), name, role_code
- Stadium: id (nombre normalizado), name, address
- Referee: id (nombre normalizado), name, committee
- Goal: id, minute (int), scoreline_home (int), scoreline_away (int), scorer_name, scoring_team ("home"/"away"), type ("regular"/"own"/"penalty")
- Card: id, minute (int), color ("yellow"/"red"), target_kind ("player"/"coach"), target_name, team ("home"/"away")

Relaciones:
- (Match)-[:HOME_TEAM]->(Team)
- (Match)-[:AWAY_TEAM]->(Team)
- (Match)-[:PLAYED_AT]->(Stadium)
- (Match)-[:OFFICIATED_BY]->(Referee)
- (Match)-[:HAS_GOAL]->(Goal)
- (Match)-[:HAS_CARD]->(Card)
- (Goal)-[:SCORED_BY]->(Player)
- (Goal)-[:FOR_TEAM]->(Team)
- (Card)-[:GIVEN_TO_PLAYER]->(Player)
- (Card)-[:GIVEN_TO_COACH]->(Coach)
- (Card)-[:AGAINST]->(Team)
- (Player)-[:APPEARED_IN {role, jersey}]->(Match)
- (Player)-[:PLAYS_FOR {match_id}]->(Team)
- (Coach)-[:COACHED {match_id}]->(Team)

Convenciones de búsqueda:
- Los IDs son nombres normalizados: sin acentos, en MAYÚSCULAS, espacios colapsados.
- Para buscar por nombre de jugadora o equipo usa: WHERE p.id CONTAINS toUpper('nombre')
- Ejemplo: MATCH (p:Player) WHERE p.id CONTAINS toUpper('garcia') RETURN p.name
- Para filtros de texto parcial también puedes usar: WHERE toLower(p.name) CONTAINS toLower('garcia')
"""


def graph_schema_summary() -> str:
    """Return a curated schema description for use in the agent system prompt."""
    try:
        with Neo4jClient() as client:
            labels = [r["label"] for r in client.run_read("CALL db.labels() YIELD label RETURN label ORDER BY label")]
            rel_types = [r["relationshipType"] for r in client.run_read("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType")]
        live_info = f"\nLabels en el grafo: {', '.join(labels)}\nTipos de relación: {', '.join(rel_types)}\n"
    except Exception:
        live_info = ""

    return _ONTOLOGY_PROSE + live_info
