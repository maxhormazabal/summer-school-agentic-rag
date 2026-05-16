import unicodedata
import re


def normalize_name(s: str) -> str:
    """Normalize a name: strip accents, uppercase, collapse whitespace."""
    nfkd = unicodedata.normalize("NFKD", s)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", ascii_str).upper().strip()


def player_id(full_name: str) -> str:
    return normalize_name(full_name)


def team_id(name: str) -> str:
    return normalize_name(name)


def stadium_id(name: str) -> str:
    return normalize_name(name)


def referee_id(name: str) -> str:
    return normalize_name(name)


def coach_id(full_name: str) -> str:
    return normalize_name(full_name)


def match_id(home: str, away: str, journey: int) -> str:
    return f"{team_id(home)}__VS__{team_id(away)}__J{journey}"


def goal_id(mid: str, idx: int) -> str:
    return f"{mid}__GOAL_{idx}"


def card_id(mid: str, idx: int) -> str:
    return f"{mid}__CARD_{idx}"
