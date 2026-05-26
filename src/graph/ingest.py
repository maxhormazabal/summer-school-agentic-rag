from __future__ import annotations

import json
from pathlib import Path

from src.common import ids as ID
from src.common.logging import console
from src.common.paths import EXTRACTED_DIR, EXTRACTED_FULL_DIR
from src.graph.neo4j_client import Neo4jClient
from src.ontology.schema import CardTargetKind, MatchExtraction

_NODE_LABELS = ["Match", "Team", "Player", "Coach", "Stadium", "Referee", "Goal", "Card"]


def _count_labels(client: Neo4jClient) -> dict[str, int]:
    """Return node counts per label using an existing client."""
    counts: dict[str, int] = {}
    for label in _NODE_LABELS:
        result = client.run_read(f"MATCH (n:{label}) RETURN count(n) AS c")
        counts[label] = result[0]["c"] if result else 0
    return counts


def ingest_match(data: MatchExtraction, client: Neo4jClient | None = None) -> None:
    """Ingest a single match into Neo4J using MERGE (idempotent).

    Pass an existing ``client`` to reuse one driver across many matches (see
    :func:`ingest_full`); when omitted a short-lived client is opened. Each entity category
    (players, coaches, goals, cards) is written in a single ``UNWIND`` round-trip instead of
    one per row — ~5 statements per match instead of ~30, which matters over cloud latency.
    """
    if client is None:
        with Neo4jClient() as own:
            _ingest_match(own, data)
    else:
        _ingest_match(client, data)


def _ingest_match(client: Neo4jClient, data: MatchExtraction) -> None:
    mid = ID.match_id(data.home.name, data.away.name, data.journey)
    home_id = ID.team_id(data.home.name)
    away_id = ID.team_id(data.away.name)
    stadium_id = ID.stadium_id(data.stadium.name)
    referee_id = ID.referee_id(data.referee.name)

    # Match + Teams + Stadium + Referee (one statement).
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
        mid=mid, journey=data.journey, competition=data.competition, status=data.status,
        score_home=data.score_home, score_away=data.score_away,
        home_id=home_id, home_name=data.home.name, away_id=away_id, away_name=data.away.name,
        stadium_id=stadium_id, stadium_name=data.stadium.name, stadium_addr=data.stadium.address,
        referee_id=referee_id, referee_name=data.referee.name, referee_committee=data.referee.committee,
    )

    # Players (both lineups) — one statement.
    players = [
        {"pid": ID.player_id(e.player.name), "pname": e.player.name, "tid": tid,
         "role": e.role.value, "jersey": e.player.jersey}
        for team_obj, tid in [(data.home, home_id), (data.away, away_id)]
        for e in team_obj.lineup
    ]
    if players:
        client.run_write(
            """
            UNWIND $players AS pl
            MERGE (p:Player {id: pl.pid}) SET p.name = pl.pname
            WITH p, pl
            MATCH (m:Match {id: $mid})
            MATCH (t:Team {id: pl.tid})
            MERGE (p)-[ai:APPEARED_IN]->(m) SET ai.role = pl.role, ai.jersey = pl.jersey
            MERGE (p)-[:PLAYS_FOR {match_id: $mid}]->(t)
            """,
            players=players, mid=mid,
        )

    # Coaches (both teams) — one statement.
    coaches = [
        {"cid": ID.coach_id(c.name), "cname": c.name, "role_code": c.role_code, "tid": tid}
        for team_obj, tid in [(data.home, home_id), (data.away, away_id)]
        for c in team_obj.coaches
    ]
    if coaches:
        client.run_write(
            """
            UNWIND $coaches AS co
            MERGE (c:Coach {id: co.cid}) SET c.name = co.cname, c.role_code = co.role_code
            WITH c, co
            MATCH (t:Team {id: co.tid})
            MERGE (c)-[:COACHED {match_id: $mid}]->(t)
            """,
            coaches=coaches, mid=mid,
        )

    # Goals — one statement; SCORED_BY only if the scorer's Player node exists.
    goals = [
        {"gid": ID.goal_id(mid, idx), "minute": g.minute,
         "sl_home": g.scoreline_home, "sl_away": g.scoreline_away,
         "scorer_name": g.scorer_name, "scoring_team": g.scoring_team, "gtype": g.type.value,
         "team_id": home_id if g.scoring_team == "home" else away_id,
         "scorer_pid": ID.player_id(g.scorer_name)}
        for idx, g in enumerate(data.goals)
    ]
    if goals:
        client.run_write(
            """
            UNWIND $goals AS gl
            MERGE (g:Goal {id: gl.gid})
              SET g.minute = gl.minute, g.scoreline_home = gl.sl_home, g.scoreline_away = gl.sl_away,
                  g.scorer_name = gl.scorer_name, g.scoring_team = gl.scoring_team, g.type = gl.gtype
            WITH g, gl
            MATCH (m:Match {id: $mid})
            MATCH (t:Team {id: gl.team_id})
            MERGE (m)-[:HAS_GOAL]->(g)
            MERGE (g)-[:FOR_TEAM]->(t)
            WITH g, gl
            OPTIONAL MATCH (p:Player {id: gl.scorer_pid})
            FOREACH (_ IN CASE WHEN p IS NULL THEN [] ELSE [1] END | MERGE (g)-[:SCORED_BY]->(p))
            """,
            goals=goals, mid=mid,
        )

    # Cards — split by recipient kind so each batch has a fixed label/relationship type.
    def _card_rows(kind: CardTargetKind) -> list[dict]:
        rows = []
        for idx, card in enumerate(data.cards):
            if card.target_kind != kind:
                continue
            target_id = (ID.player_id(card.target_name) if kind == CardTargetKind.player
                         else ID.coach_id(card.target_name))
            rows.append({
                "cid": ID.card_id(mid, idx), "minute": card.minute, "color": card.color.value,
                "target_kind": card.target_kind.value, "target_name": card.target_name,
                "team": card.team, "card_team_id": home_id if card.team == "home" else away_id,
                "target_id": target_id,
            })
        return rows

    for kind, target_label, rel_type in [
        (CardTargetKind.player, "Player", "GIVEN_TO_PLAYER"),
        (CardTargetKind.coach, "Coach", "GIVEN_TO_COACH"),
    ]:
        rows = _card_rows(kind)
        if not rows:
            continue
        client.run_write(
            f"""
            UNWIND $cards AS cd
            MERGE (card:Card {{id: cd.cid}})
              SET card.minute = cd.minute, card.color = cd.color,
                  card.target_kind = cd.target_kind, card.target_name = cd.target_name, card.team = cd.team
            WITH card, cd
            MATCH (m:Match {{id: $mid}})
            MATCH (t:Team {{id: cd.card_team_id}})
            MERGE (m)-[:HAS_CARD]->(card)
            MERGE (card)-[:AGAINST]->(t)
            WITH card, cd
            OPTIONAL MATCH (target:{target_label} {{id: cd.target_id}})
            FOREACH (_ IN CASE WHEN target IS NULL THEN [] ELSE [1] END |
                     MERGE (card)-[:{rel_type}]->(target))
            """,
            cards=rows, mid=mid,
        )


def ingest_all() -> dict[str, int]:
    """Ingest all extracted JSON files and return node counts by label."""
    json_files = sorted(EXTRACTED_DIR.glob("example*.json"))
    if not json_files:
        console.print("[yellow]No extracted JSONs found in data/extracted/. Run stage2 first.[/yellow]")
        return {}

    with Neo4jClient() as client:
        for jf in json_files:
            console.print(f"[cyan]Ingesting {jf.name}...[/cyan]")
            data = MatchExtraction.model_validate_json(jf.read_text(encoding="utf-8"))
            ingest_match(data, client=client)
            console.print(f"[green]Done: {jf.name}[/green]")
        return _count_labels(client)


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
    with Neo4jClient() as client:
        for i, jf in enumerate(json_files, 1):
            data = MatchExtraction.model_validate_json(jf.read_text(encoding="utf-8"))
            ingest_match(data, client=client)
            if i % progress_every == 0 or i == total:
                console.print(f"[green]  ingested {i}/{total}[/green]")
        return _count_labels(client)
