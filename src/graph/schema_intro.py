from __future__ import annotations

from src.graph.neo4j_client import Neo4jClient

_ONTOLOGY_PROSE = """\
The database contains information about FCF (Federació Catalana de Futbol) football matches.

Nodes and main properties:
- Match: id (unique string), journey (int), competition, status, score_home (int), score_away (int)
- Team: id (normalised name), name
- Player: id (normalised name), name
- Coach: id (normalised name), name, role_code
- Stadium: id (normalised name), name, address
- Referee: id (normalised name), name, committee
- Goal: id, minute (int), scoreline_home (int), scoreline_away (int), scorer_name, scoring_team ("home"/"away"), type ("regular"/"own"/"penalty")
- Card: id, minute (int), color ("yellow"/"red"), target_kind ("player"/"coach"), target_name, team ("home"/"away")

Relationships:
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

Search conventions:
- IDs are normalised names: no accents, UPPERCASE, collapsed whitespace.
- To search by player or team name use: WHERE p.id CONTAINS toUpper('name')
- Example: MATCH (p:Player) WHERE p.id CONTAINS toUpper('garcia') RETURN p.name
- For partial text filters you can also use: WHERE toLower(p.name) CONTAINS toLower('garcia')
"""


def graph_schema_summary() -> str:
    """Return a curated schema description for use in the agent system prompt."""
    try:
        with Neo4jClient() as client:
            labels = [r["label"] for r in client.run_read("CALL db.labels() YIELD label RETURN label ORDER BY label")]
            rel_types = [r["relationshipType"] for r in client.run_read("CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType ORDER BY relationshipType")]
        live_info = f"\nGraph labels: {', '.join(labels)}\nRelationship types: {', '.join(rel_types)}\n"
    except Exception:
        live_info = ""

    return _ONTOLOGY_PROSE + live_info
