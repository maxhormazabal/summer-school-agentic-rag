from __future__ import annotations

import json
from pathlib import Path

from src.common import ids as ID
from src.common.logging import console
from src.common.paths import EXTRACTED_DIR, EXTRACTED_FULL_DIR
from src.graph.neo4j_client import Neo4jClient
from src.ontology.schema import CardTargetKind, MatchExtraction


def ingest_match(data: MatchExtraction) -> None:
    """Ingest a single match into Neo4J using MERGE (idempotent)."""
    mid = ID.match_id(data.home.name, data.away.name, data.journey)
    home_id = ID.team_id(data.home.name)
    away_id = ID.team_id(data.away.name)
    stadium_id = ID.stadium_id(data.stadium.name)
    referee_id = ID.referee_id(data.referee.name)

    with Neo4jClient() as client:
        # Match + Teams + Stadium + Referee
        client.run_write(
            """
            MERGE (m:Match {id: $mid})
              SET m.journey = $journey, m.competition = $competition,
                  m.status = $status, m.score_home = $score_home,
                  m.score_away = $score_away
            MERGE (th:Team {id: $home_id})  SET th.name = $home_name
            MERGE (ta:Team {id: $away_id})  SET ta.name = $away_name
            MERGE (s:Stadium {id: $stadium_id}) SET s.name = $stadium_name, s.address = $stadium_addr
            MERGE (r:Referee {id: $referee_id}) SET r.name = $referee_name, r.committee = $referee_committee
            MERGE (m)-[:HOME_TEAM]->(th)
            MERGE (m)-[:AWAY_TEAM]->(ta)
            MERGE (m)-[:PLAYED_AT]->(s)
            MERGE (m)-[:OFFICIATED_BY]->(r)
            """,
            mid=mid,
            journey=data.journey,
            competition=data.competition,
            status=data.status,
            score_home=data.score_home,
            score_away=data.score_away,
            home_id=home_id,
            home_name=data.home.name,
            away_id=away_id,
            away_name=data.away.name,
            stadium_id=stadium_id,
            stadium_name=data.stadium.name,
            stadium_addr=data.stadium.address,
            referee_id=referee_id,
            referee_name=data.referee.name,
            referee_committee=data.referee.committee,
        )

        # Players (lineups)
        for team_obj, tid in [(data.home, home_id), (data.away, away_id)]:
            for entry in team_obj.lineup:
                pid = ID.player_id(entry.player.name)
                client.run_write(
                    """
                    MERGE (p:Player {id: $pid}) SET p.name = $pname
                    MERGE (m:Match {id: $mid})
                    MERGE (t:Team {id: $tid})
                    MERGE (p)-[:APPEARED_IN {role: $role, jersey: $jersey}]->(m)
                    MERGE (p)-[:PLAYS_FOR {match_id: $mid}]->(t)
                    """,
                    pid=pid,
                    pname=entry.player.name,
                    mid=mid,
                    tid=tid,
                    role=entry.role.value,
                    jersey=entry.player.jersey,
                )

        # Coaches
        for team_obj, tid in [(data.home, home_id), (data.away, away_id)]:
            for coach in team_obj.coaches:
                cid = ID.coach_id(coach.name)
                client.run_write(
                    """
                    MERGE (c:Coach {id: $cid}) SET c.name = $cname, c.role_code = $role_code
                    MERGE (t:Team {id: $tid})
                    MERGE (c)-[:COACHED {match_id: $mid}]->(t)
                    """,
                    cid=cid,
                    cname=coach.name,
                    role_code=coach.role_code,
                    tid=tid,
                    mid=mid,
                )

        # Goals
        for idx, goal in enumerate(data.goals):
            gid = ID.goal_id(mid, idx)
            team_id_for_goal = home_id if goal.scoring_team == "home" else away_id

            # Resolve scorer to a player node (best-effort by normalized name)
            scorer_pid = ID.player_id(goal.scorer_name)

            client.run_write(
                """
                MERGE (g:Goal {id: $gid})
                  SET g.minute = $minute,
                      g.scoreline_home = $sl_home, g.scoreline_away = $sl_away,
                      g.scorer_name = $scorer_name, g.scoring_team = $scoring_team,
                      g.type = $gtype
                MERGE (m:Match {id: $mid})
                MERGE (t:Team {id: $team_id})
                MERGE (m)-[:HAS_GOAL]->(g)
                MERGE (g)-[:FOR_TEAM]->(t)
                """,
                gid=gid,
                minute=goal.minute,
                sl_home=goal.scoreline_home,
                sl_away=goal.scoreline_away,
                scorer_name=goal.scorer_name,
                scoring_team=goal.scoring_team,
                gtype=goal.type.value,
                mid=mid,
                team_id=team_id_for_goal,
            )
            # Link to Player node if it already exists (MERGE won't create a dangling node)
            client.run_write(
                """
                MATCH (g:Goal {id: $gid})
                MATCH (p:Player {id: $scorer_pid})
                MERGE (g)-[:SCORED_BY]->(p)
                """,
                gid=gid,
                scorer_pid=scorer_pid,
            )

        # Cards
        for idx, card in enumerate(data.cards):
            cid = ID.card_id(mid, idx)
            card_team_id = home_id if card.team == "home" else away_id
            target_id = (
                ID.player_id(card.target_name)
                if card.target_kind == CardTargetKind.player
                else ID.coach_id(card.target_name)
            )
            rel_type = (
                "GIVEN_TO_PLAYER"
                if card.target_kind == CardTargetKind.player
                else "GIVEN_TO_COACH"
            )
            target_label = "Player" if card.target_kind == CardTargetKind.player else "Coach"

            client.run_write(
                f"""
                MERGE (card:Card {{id: $cid}})
                  SET card.minute = $minute, card.color = $color,
                      card.target_kind = $target_kind, card.target_name = $target_name,
                      card.team = $team
                MERGE (m:Match {{id: $mid}})
                MERGE (t:Team {{id: $card_team_id}})
                MERGE (m)-[:HAS_CARD]->(card)
                MERGE (card)-[:AGAINST]->(t)
                """,
                cid=cid,
                minute=card.minute,
                color=card.color.value,
                target_kind=card.target_kind.value,
                target_name=card.target_name,
                team=card.team,
                mid=mid,
                card_team_id=card_team_id,
            )
            # Link to Player or Coach node if it exists
            client.run_write(
                f"""
                MATCH (card:Card {{id: $cid}})
                MATCH (target:{target_label} {{id: $target_id}})
                MERGE (card)-[:{rel_type}]->(target)
                """,
                cid=cid,
                target_id=target_id,
            )


def ingest_all() -> dict[str, int]:
    """Ingest all extracted JSON files and return node counts by label."""
    json_files = sorted(EXTRACTED_DIR.glob("example*.json"))
    if not json_files:
        console.print("[yellow]No extracted JSONs found in data/extracted/. Run stage2 first.[/yellow]")
        return {}

    for jf in json_files:
        console.print(f"[cyan]Ingesting {jf.name}...[/cyan]")
        data = MatchExtraction.model_validate_json(jf.read_text(encoding="utf-8"))
        ingest_match(data)
        console.print(f"[green]Done: {jf.name}[/green]")

    # Return counts per label
    counts: dict[str, int] = {}
    with Neo4jClient() as client:
        for label in ["Match", "Team", "Player", "Coach", "Stadium", "Referee", "Goal", "Card"]:
            result = client.run_read(f"MATCH (n:{label}) RETURN count(n) AS c")
            counts[label] = result[0]["c"] if result else 0
    return counts


def _resolve_full_dir(directory: Path | None) -> Path:
    """Resolve the directory holding the bulk JSONs.

    Bulk outputs are model-namespaced: ``data/extracted_full/<model-tag>/*.json``.
    If ``directory`` already holds JSONs use it; otherwise descend into the single
    model-tag subdir that contains JSONs. Raises if the choice is ambiguous so the
    caller passes an explicit path rather than ingesting the wrong model's output.
    """
    base = Path(directory) if directory is not None else EXTRACTED_FULL_DIR
    if any(base.glob("*.json")):
        return base
    if not base.exists():
        return base
    candidates = [
        d for d in sorted(base.iterdir())
        if d.is_dir() and not d.name.startswith("_") and any(d.glob("*.json"))
    ]
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        names = ", ".join(d.name for d in candidates)
        raise ValueError(
            f"Multiple model-tag subdirs with JSONs under {base} ({names}); "
            "pass an explicit `directory=` to disambiguate."
        )
    return base


def ingest_full(directory: Path | None = None, progress_every: int = 100) -> dict[str, int]:
    """Ingest the bulk dataset (`data/extracted_full/<model-tag>/*.json`).

    Mirrors :func:`ingest_all` exactly — same labels, same deterministic IDs via
    `src.common.ids`, same MERGE-based `ingest_match` — only the source directory and
    progress logging differ. `ingest_all` (the 3-example path used by `tutorial.py`)
    is left untouched.
    """
    src_dir = _resolve_full_dir(directory)
    json_files = sorted(src_dir.glob("*.json"))
    if not json_files:
        console.print(
            f"[yellow]No JSONs found under {src_dir}. Download/extract the bulk dataset first.[/yellow]"
        )
        return {}

    total = len(json_files)
    console.print(f"[cyan]Ingesting {total} match reports from {src_dir}...[/cyan]")
    for i, jf in enumerate(json_files, 1):
        data = MatchExtraction.model_validate_json(jf.read_text(encoding="utf-8"))
        ingest_match(data)
        if i % progress_every == 0 or i == total:
            console.print(f"[green]  ingested {i}/{total}[/green]")

    counts: dict[str, int] = {}
    with Neo4jClient() as client:
        for label in ["Match", "Team", "Player", "Coach", "Stadium", "Referee", "Goal", "Card"]:
            result = client.run_read(f"MATCH (n:{label}) RETURN count(n) AS c")
            counts[label] = result[0]["c"] if result else 0
    return counts
