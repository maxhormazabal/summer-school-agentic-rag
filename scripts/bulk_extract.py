"""
Bulk VLM extraction: every PNG in `data/images_full/` → JSON in `data/extracted_full/`.

Designed to be run **out of the notebook**. Idempotent: skips PNGs whose JSON already exists.
Safe to interrupt; just re-run to resume.

Backend selection (`--provider` flag or `VLM_PROVIDER` env var):
- `openai` (default): uses `src.extraction.vlm_extractor.extract` — GPT-4o vision via API.
- `local`: uses `src.extraction.vlm_local.extract` — locally-hosted VLM (server-only).

Concurrency notes:
- For `openai`: 10–20 workers is sane (OpenAI Tier 1 ≈ 500 RPM, well above what threads will do).
- For `local`: usually `--workers 1` — GPU inference is its own pipeline; threading does not help.

Outputs:
- JSON per PNG at `data/extracted_full/<stem>.json` (validated `MatchExtraction`).
- `data/extracted_full/_failures.jsonl` — append-only log of files that errored, one per line:
    {"file": "...", "error": "...", "traceback": "..."}

Soft warnings (logged, do NOT block):
- `len(goals) != score_home + score_away` — VLM may have miscounted under occlusion.
- A scorer whose normalized name does not match any lineup entry of its team — possible typo.

Usage:
    python scripts/bulk_extract.py                            # OpenAI, 15 workers
    python scripts/bulk_extract.py --provider local --workers 1
    python scripts/bulk_extract.py --limit 5                  # smoke test
    python scripts/bulk_extract.py --retry-failures           # only re-try files in _failures.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow `python scripts/bulk_extract.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.ids import normalize_name  # noqa: E402
from src.common.logging import console  # noqa: E402
from src.common.paths import EXTRACTED_FULL_DIR, IMAGES_FULL_DIR  # noqa: E402
from src.ontology.schema import MatchExtraction  # noqa: E402


def _get_extractor(provider: str):
    """Return the extract() callable for the chosen backend."""
    if provider == "openai":
        from src.extraction.vlm_extractor import extract
        return extract
    if provider == "local":
        from src.extraction.vlm_local import extract
        return extract
    raise ValueError(f"Unknown provider: {provider!r}. Use 'openai' or 'local'.")


def _soft_validate(match: MatchExtraction, name: str) -> list[str]:
    """Emit warnings (not errors) for invariants the VLM commonly violates."""
    warnings: list[str] = []
    expected = match.score_home + match.score_away
    actual = len(match.goals)
    if expected != actual:
        warnings.append(f"goals_count_mismatch:expected={expected},actual={actual}")

    home_ids = {normalize_name(e.player.name) for e in match.home.lineup}
    away_ids = {normalize_name(e.player.name) for e in match.away.lineup}
    for i, g in enumerate(match.goals):
        team_ids = home_ids if g.scoring_team == "home" else away_ids
        if normalize_name(g.scorer_name) not in team_ids:
            warnings.append(f"scorer_not_in_lineup[{i}]:{g.scorer_name!r}({g.scoring_team})")
    return warnings


def _extract_one(image_path: Path, out_dir: Path, extractor) -> dict:
    """Process a single image. Returns a status dict (never raises)."""
    out_path = out_dir / (image_path.stem + ".json")
    if out_path.exists():
        return {"file": image_path.name, "status": "cached", "warnings": []}

    try:
        match = extractor(image_path)
    except Exception as exc:  # noqa: BLE001
        return {
            "file": image_path.name,
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=4),
        }

    warnings = _soft_validate(match, image_path.name)
    out_path.write_text(match.model_dump_json(indent=2), encoding="utf-8")
    return {"file": image_path.name, "status": "ok", "warnings": warnings}


def _load_retry_set(failures_file: Path) -> set[str]:
    """Return the set of filenames in the failures log (for --retry-failures)."""
    if not failures_file.exists():
        return set()
    names: set[str] = set()
    for line in failures_file.read_text().splitlines():
        try:
            names.add(json.loads(line)["file"])
        except (json.JSONDecodeError, KeyError):
            continue
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=IMAGES_FULL_DIR,
                        help="PNG source directory (default: data/images_full/)")
    parser.add_argument("--output-dir", type=Path, default=EXTRACTED_FULL_DIR,
                        help="JSON output directory (default: data/extracted_full/)")
    parser.add_argument("--provider", choices=["openai", "local"],
                        default=os.environ.get("VLM_PROVIDER", "openai"),
                        help="VLM backend (default: env VLM_PROVIDER or 'openai')")
    parser.add_argument("--workers", type=int, default=15,
                        help="Parallel workers (default: 15 for openai; set 1 for local)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N PNGs (smoke test)")
    parser.add_argument("--retry-failures", action="store_true",
                        help="Only re-process files listed in _failures.jsonl")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    failures_file = args.output_dir / "_failures.jsonl"

    extractor = _get_extractor(args.provider)

    pngs = sorted(args.input_dir.glob("*.png"))
    if args.retry_failures:
        retry = _load_retry_set(failures_file)
        pngs = [p for p in pngs if p.name in retry]
        if failures_file.exists():
            failures_file.unlink()  # fresh log
        console.print(f"[yellow]Retry mode: {len(pngs)} files from _failures.jsonl[/yellow]")

    if args.limit:
        pngs = pngs[: args.limit]

    if not pngs:
        console.print("[yellow]Nothing to do.[/yellow]")
        return 0

    console.print(f"[bold]Bulk extraction[/bold]: {len(pngs)} files, provider={args.provider}, workers={args.workers}")
    console.print(f"  source: {args.input_dir}")
    console.print(f"  target: {args.output_dir}")

    started = time.time()
    counts = {"ok": 0, "cached": 0, "error": 0, "warned": 0}
    failure_log: list[dict] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_extract_one, p, args.output_dir, extractor): p for p in pngs}
        for i, fut in enumerate(as_completed(futures), 1):
            result = fut.result()
            if result["status"] == "ok":
                counts["ok"] += 1
                if result["warnings"]:
                    counts["warned"] += 1
            elif result["status"] == "cached":
                counts["cached"] += 1
            else:
                counts["error"] += 1
                failure_log.append(result)

            if i % 25 == 0 or i == len(pngs):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(pngs) - i) / rate if rate else 0
                console.print(
                    f"  [{i:4d}/{len(pngs)}] ok={counts['ok']} cached={counts['cached']} "
                    f"warned={counts['warned']} err={counts['error']} "
                    f"({rate:.2f}/s, ETA {eta / 60:.1f}min)"
                )

    if failure_log:
        with failures_file.open("a", encoding="utf-8") as fh:
            for f in failure_log:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        console.print(f"\n[red]{len(failure_log)} failures logged to {failures_file.name}[/red]")
        console.print("  Re-run with --retry-failures after diagnosing.")

    elapsed = time.time() - started
    console.print(f"\n[bold green]Done in {elapsed / 60:.1f}min[/bold green]: {counts}")
    return 0 if counts["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
