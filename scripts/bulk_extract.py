"""
Bulk VLM extraction: every PNG in `data/images_full/` → JSON in
`data/extracted_full/<model-tag>/`.

Designed to be run **out of the notebook**. Idempotent: skips PNGs whose JSON already exists.
Safe to interrupt; just re-run to resume.

Backend selection (`--provider` flag or `VLM_PROVIDER` env var):
- `openai` (default): uses `src.extraction.vlm_extractor.extract` — GPT-4o vision via API.
- `local`: uses `src.extraction.vlm_local.extract` — locally-hosted Qwen3-VL (or other).

Outputs (model-namespaced so different models can coexist):
    data/extracted_full/<model-tag>/<stem>.json
    data/extracted_full/<model-tag>/_failures[-shard-N].jsonl

`--model-tag` overrides the default tag (openai → 'openai-gpt-4o', local → `vlm_local.model_slug()`).

Sharding (for multi-GPU parallelism):
    --shard I/N    Process only the I-th shard out of N (1-indexed). Each shard writes its
                   failures to `_failures-shard-<I>.jsonl` so concurrent workers do not stomp
                   on each other. `scripts/bulk_extract_local.py` wraps this for you.

Concurrency notes:
- For `openai`: 10–20 threads is sane.
- For `local`: keep `--workers 1`; GPU inference is serial. Use the orchestrator for multi-GPU.

Soft warnings (logged, do NOT block):
- `len(goals) != score_home + score_away` — VLM may have miscounted under occlusion.
- A scorer whose normalized name does not match any lineup entry — possible typo.

Usage:
    python scripts/bulk_extract.py                                   # openai, 15 workers
    python scripts/bulk_extract.py --provider local --workers 1
    python scripts/bulk_extract.py --limit 5                         # smoke test
    python scripts/bulk_extract.py --retry-failures                  # only re-try logged failures
    python scripts/bulk_extract.py --provider local --shard 1/4      # shard 1 of 4 (multi-GPU)
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.common.ids import normalize_name  # noqa: E402
from src.common.logging import console  # noqa: E402
from src.common.paths import EXTRACTED_FULL_DIR, IMAGES_FULL_DIR  # noqa: E402
from src.ontology.schema import MatchExtraction  # noqa: E402


def _get_extractor(provider: str):
    if provider == "openai":
        from src.extraction.vlm_extractor import extract
        return extract
    if provider == "local":
        from src.extraction.vlm_local import extract
        return extract
    raise ValueError(f"Unknown provider: {provider!r}. Use 'openai' or 'local'.")


def _default_model_tag(provider: str) -> str:
    if provider == "openai":
        return "openai-gpt-4o"
    if provider == "local":
        from src.extraction.vlm_local import model_slug
        return model_slug()
    raise ValueError(provider)


def _soft_validate(match: MatchExtraction, name: str) -> list[str]:
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
    if not failures_file.exists():
        return set()
    names: set[str] = set()
    for line in failures_file.read_text().splitlines():
        try:
            names.add(json.loads(line)["file"])
        except (json.JSONDecodeError, KeyError):
            continue
    return names


def _parse_shard(spec: str) -> tuple[int, int]:
    try:
        i_str, n_str = spec.split("/", 1)
        i, n = int(i_str), int(n_str)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"--shard must be I/N (e.g. 1/4), got {spec!r}") from exc
    if not (1 <= i <= n):
        raise argparse.ArgumentTypeError(f"--shard I must satisfy 1 <= I <= N, got {spec!r}")
    return i, n


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, default=IMAGES_FULL_DIR,
                        help="PNG source directory (default: data/images_full/)")
    parser.add_argument("--output-root", type=Path, default=EXTRACTED_FULL_DIR,
                        help="Root output dir; outputs land in <root>/<model-tag>/")
    parser.add_argument("--provider", choices=["openai", "local"],
                        default=os.environ.get("VLM_PROVIDER", "openai"))
    parser.add_argument("--model-tag", type=str, default=None,
                        help="Override the default subfolder tag (e.g. 'qwen3-vl-8b-instruct')")
    parser.add_argument("--workers", type=int, default=15,
                        help="Thread workers (15 for openai; 1 for local)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N PNGs (smoke test)")
    parser.add_argument("--retry-failures", action="store_true")
    parser.add_argument("--shard", type=_parse_shard, default=None, metavar="I/N",
                        help="Process only shard I out of N (1-indexed). Used by the multi-GPU runner.")
    args = parser.parse_args()

    model_tag = args.model_tag or _default_model_tag(args.provider)
    output_dir = args.output_root / model_tag
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.shard:
        shard_i, shard_n = args.shard
        failures_file = output_dir / f"_failures-shard-{shard_i}.jsonl"
    else:
        shard_i = shard_n = None
        failures_file = output_dir / "_failures.jsonl"

    extractor = _get_extractor(args.provider)

    pngs = sorted(args.input_dir.glob("*.png"))
    if args.retry_failures:
        retry = _load_retry_set(failures_file)
        pngs = [p for p in pngs if p.name in retry]
        if failures_file.exists():
            failures_file.unlink()
        console.print(f"[yellow]Retry mode: {len(pngs)} files from {failures_file.name}[/yellow]")

    if args.shard:
        pngs = [p for idx, p in enumerate(pngs) if (idx % shard_n) == (shard_i - 1)]

    if args.limit:
        pngs = pngs[: args.limit]

    if not pngs:
        console.print("[yellow]Nothing to do.[/yellow]")
        return 0

    shard_label = f", shard {shard_i}/{shard_n}" if args.shard else ""
    console.print(
        f"[bold]Bulk extraction[/bold]: {len(pngs)} files, provider={args.provider}, "
        f"tag={model_tag}, workers={args.workers}{shard_label}"
    )
    console.print(f"  source: {args.input_dir}")
    console.print(f"  target: {output_dir}")

    started = time.time()
    counts = {"ok": 0, "cached": 0, "error": 0, "warned": 0}
    failure_log: list[dict] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_extract_one, p, output_dir, extractor): p for p in pngs}
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

    elapsed = time.time() - started
    console.print(f"\n[bold green]Done in {elapsed / 60:.1f}min[/bold green]: {counts}")
    return 0 if counts["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
