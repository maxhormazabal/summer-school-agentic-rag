"""Verify the SUPLENTS prompt fix on a hand-picked set of bad actas.

Re-extracts each with vlm_local.extract() (now using the emphasized prompt),
writes new JSON to data/extracted_full/_verify/, and prints an old-vs-new
comparison: per-team starter/sub counts, goal-count check, scorer-in-lineup.
Originals are NOT touched. Throwaway diagnostic.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.ids import normalize_name
from src.extraction import vlm_local as V

STEMS = ["1", "10", "100", "554", "656", "687", "1001", "1003", "1105", "1153", "1383", "1398"]
OLD_DIR = Path("data/extracted_full/qwen3-vl-8b-instruct")
IMG_DIR = Path("data/images_full")
OUT_DIR = Path("data/extracted_full/_verify")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def stats(d: dict) -> dict:
    out = {}
    for side in ("home", "away"):
        roles = [e["role"] for e in d[side]["lineup"]]
        out[side] = (
            sum(1 for r in roles if str(r).endswith("starter")),
            sum(1 for r in roles if str(r).endswith("sub")),
        )
    exp = d["score_home"] + d["score_away"]
    act = len(d["goals"])
    home = {normalize_name(e["player"]["name"]) for e in d["home"]["lineup"]}
    away = {normalize_name(e["player"]["name"]) for e in d["away"]["lineup"]}
    miss = 0
    for g in d["goals"]:
        team = home if g["scoring_team"] == "home" else away
        if normalize_name(g["scorer_name"]) not in team:
            miss += 1
    out["goals"] = (exp, act)
    out["scorer_miss"] = miss
    return out


def fmt(s: dict) -> str:
    return (
        f"home={s['home'][0]}st/{s['home'][1]}sub  away={s['away'][0]}st/{s['away'][1]}sub  "
        f"goals exp={s['goals'][0]}/act={s['goals'][1]}  scorer_miss={s['scorer_miss']}"
    )


for stem in STEMS:
    old = json.loads((OLD_DIR / f"{stem}.json").read_text())
    t0 = time.time()
    new_model = V.extract(IMG_DIR / f"{stem}.png")
    dt = time.time() - t0
    new = json.loads(new_model.model_dump_json())
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(new, ensure_ascii=False, indent=2))
    print(f"\n### {stem}  ({dt:.0f}s)", flush=True)
    print(f"  OLD: {fmt(stats(old))}", flush=True)
    print(f"  NEW: {fmt(stats(new))}", flush=True)
