"""
Multi-GPU orchestrator for the local VLM backend.

Auto-detects free GPUs (via `nvidia-smi`), splits the PNG list into N shards (N = number of
free GPUs, or `--gpus` override), and spawns one worker subprocess per GPU. Each worker runs
`scripts/bulk_extract.py --provider local --shard I/N`, pinned to its GPU via
`CUDA_VISIBLE_DEVICES`. Workers write JSONs to a shared model-namespaced directory
(`data/extracted_full/<model-tag>/`) and per-shard failure logs.

Usage:
    python scripts/bulk_extract_local.py                       # use all "free" GPUs
    python scripts/bulk_extract_local.py --gpus 1,2,4,5        # explicit GPU list
    python scripts/bulk_extract_local.py --limit 4             # smoke test (≤4 files total)
    python scripts/bulk_extract_local.py --min-free-mb 30000   # adjust free-mem threshold
    python scripts/bulk_extract_local.py --model-tag qwen3-vl-8b-instruct
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.common.logging import console  # noqa: E402
from src.common.paths import EXTRACTED_FULL_DIR, IMAGES_FULL_DIR  # noqa: E402


def detect_free_gpus(min_free_mb: int) -> list[int]:
    """Query nvidia-smi for GPUs with at least `min_free_mb` MiB free."""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=index,memory.free", "--format=csv,noheader,nounits"],
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        console.print(f"[red]nvidia-smi failed: {exc}[/red]")
        return []

    free: list[int] = []
    for line in out.strip().splitlines():
        idx_str, mem_str = [s.strip() for s in line.split(",")]
        if int(mem_str) >= min_free_mb:
            free.append(int(idx_str))
    return free


def parse_gpu_list(spec: str) -> list[int]:
    return [int(s) for s in spec.split(",") if s.strip()]


def _default_model_tag() -> str:
    from src.extraction.vlm_local import model_slug
    return model_slug()


def count_pending(input_dir: Path, output_dir: Path) -> tuple[int, int]:
    total = len(list(input_dir.glob("*.png")))
    done = len(list(output_dir.glob("*.json")))
    return total, total - done


def merge_failures(output_dir: Path) -> int:
    """Concatenate `_failures-shard-*.jsonl` into a single `_failures.jsonl`."""
    shard_files = sorted(output_dir.glob("_failures-shard-*.jsonl"))
    if not shard_files:
        return 0
    merged = output_dir / "_failures.jsonl"
    seen: set[str] = set()
    if merged.exists():
        for line in merged.read_text().splitlines():
            try:
                seen.add(json.loads(line)["file"])
            except (json.JSONDecodeError, KeyError):
                continue
    n_new = 0
    with merged.open("a", encoding="utf-8") as out_fh:
        for f in shard_files:
            for line in f.read_text().splitlines():
                try:
                    name = json.loads(line)["file"]
                except (json.JSONDecodeError, KeyError):
                    continue
                if name in seen:
                    continue
                out_fh.write(line + "\n")
                seen.add(name)
                n_new += 1
            f.unlink()
    return n_new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input-dir", type=Path, default=IMAGES_FULL_DIR)
    parser.add_argument("--output-root", type=Path, default=EXTRACTED_FULL_DIR)
    parser.add_argument("--gpus", type=str, default=None,
                        help="Comma-separated GPU indices (e.g. '1,2,4,5'). Default: auto-detect.")
    parser.add_argument("--min-free-mb", type=int, default=30000,
                        help="When auto-detecting, require this many MiB free per GPU (default 30000).")
    parser.add_argument("--model-tag", type=str, default=None,
                        help="Output subfolder (default: derived from vlm_local model id).")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap the work to the first N pending PNGs (split across shards).")
    parser.add_argument("--retry-failures", action="store_true",
                        help="Pass --retry-failures to each shard worker.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the worker commands without running them.")
    args = parser.parse_args()

    model_tag = args.model_tag or _default_model_tag()
    output_dir = args.output_root / model_tag
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.gpus:
        gpus = parse_gpu_list(args.gpus)
    else:
        gpus = detect_free_gpus(args.min_free_mb)
    if not gpus:
        console.print("[red]No free GPUs detected. Pass --gpus explicitly or lower --min-free-mb.[/red]")
        return 2

    total, pending = count_pending(args.input_dir, output_dir)
    console.print(
        f"[bold]Multi-GPU bulk extract[/bold] · model_tag={model_tag} · gpus={gpus} ({len(gpus)} workers)"
    )
    console.print(f"  source: {args.input_dir} (total PNGs: {total})")
    console.print(f"  target: {output_dir} (pending: {pending})")

    n = len(gpus)
    cmds: list[tuple[int, list[str], dict]] = []
    for shard_i, gpu in enumerate(gpus, start=1):
        cmd = [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bulk_extract.py"),
            "--provider", "local",
            "--workers", "1",
            "--shard", f"{shard_i}/{n}",
            "--input-dir", str(args.input_dir),
            "--output-root", str(args.output_root),
            "--model-tag", model_tag,
        ]
        if args.limit:
            per_shard = -(-args.limit // n)  # ceil division
            cmd += ["--limit", str(per_shard)]
        if args.retry_failures:
            cmd.append("--retry-failures")
        env = {
            **os.environ,
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "CUDA_DEVICE_ORDER": "PCI_BUS_ID",  # align CUDA_VISIBLE_DEVICES with nvidia-smi indices
        }
        cmds.append((gpu, cmd, env))

    log_dir = output_dir / "_worker_logs"
    log_dir.mkdir(exist_ok=True)

    if args.dry_run:
        for gpu, cmd, _ in cmds:
            console.print(f"  GPU{gpu}: {' '.join(cmd)}")
        return 0

    started = time.time()
    procs = []
    for gpu, cmd, env in cmds:
        log_path = log_dir / f"gpu-{gpu}.log"
        fh = log_path.open("w", encoding="utf-8")
        p = subprocess.Popen(cmd, env=env, stdout=fh, stderr=subprocess.STDOUT, cwd=str(REPO_ROOT))
        procs.append((gpu, p, fh, log_path))
        console.print(f"  [green]launched[/green] GPU{gpu} pid={p.pid} log={log_path}")

    rc = 0
    for gpu, p, fh, log_path in procs:
        p.wait()
        fh.close()
        status = "[green]ok[/green]" if p.returncode == 0 else f"[red]exit={p.returncode}[/red]"
        console.print(f"  GPU{gpu}: {status} (log: {log_path})")
        if p.returncode != 0:
            rc = p.returncode

    n_merged = merge_failures(output_dir)
    if n_merged:
        console.print(f"  merged {n_merged} new failure entries into _failures.jsonl")

    total2, pending2 = count_pending(args.input_dir, output_dir)
    elapsed = (time.time() - started) / 60
    console.print(f"\n[bold green]Done in {elapsed:.1f}min[/bold green]: pending {pending} → {pending2}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
