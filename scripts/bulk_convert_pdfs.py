"""
One-off bulk converter: every PDF in `data/pages1793/` → PNG in `data/images_full/`.

Out-of-notebook utility. Idempotent: skips files whose PNG already exists.
Safe to interrupt and resume.

Usage:
    python scripts/bulk_convert_pdfs.py                  # default DPI=220, all files
    python scripts/bulk_convert_pdfs.py --dpi 180         # cheaper images
    python scripts/bulk_convert_pdfs.py --workers 4       # parallel conversion
    python scripts/bulk_convert_pdfs.py --limit 10        # smoke test on first 10

No model dependencies: requires only `pdf2image` and the `poppler-utils` system binary.
Runs anywhere (laptop or GPU server).
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Allow `python scripts/bulk_convert_pdfs.py` from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pdf2image import convert_from_path  # noqa: E402

from src.common.logging import console  # noqa: E402
from src.common.paths import IMAGES_FULL_DIR, PDFS_FULL_DIR  # noqa: E402


def _convert_one(pdf_path: Path, dpi: int, out_dir: Path) -> tuple[Path, str]:
    """Convert a single PDF to PNG. Returns (output_path, status)."""
    out_path = out_dir / (pdf_path.stem + ".png")
    if out_path.exists():
        return out_path, "cached"

    try:
        pages = convert_from_path(str(pdf_path), dpi=dpi)
        pages[0].save(str(out_path), "PNG")
        if len(pages) != 1:
            return out_path, f"warn:multi-page({len(pages)}, saved page 1)"
        return out_path, "ok"
    except Exception as exc:  # noqa: BLE001
        return out_path, f"error:{type(exc).__name__}:{exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=PDFS_FULL_DIR,
                        help="Directory with input PDFs (default: data/pages1793/)")
    parser.add_argument("--output-dir", type=Path, default=IMAGES_FULL_DIR,
                        help="Directory for output PNGs (default: data/images_full/)")
    parser.add_argument("--dpi", type=int, default=220,
                        help="DPI for rasterization (default: 220, matches existing extractor)")
    parser.add_argument("--workers", type=int, default=4,
                        help="Parallel conversion workers (default: 4 — CPU-bound, raise on more cores)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N PDFs (smoke test)")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)

    pdfs = sorted(args.input_dir.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]

    console.print(f"[bold]Converting {len(pdfs)} PDFs at {args.dpi} DPI[/bold]")
    console.print(f"  source: {args.input_dir}")
    console.print(f"  target: {args.output_dir}")
    console.print(f"  workers: {args.workers}")

    started = time.time()
    counts = {"ok": 0, "cached": 0, "error": 0, "warn": 0}
    errors: list[tuple[Path, str]] = []

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_convert_one, p, args.dpi, args.output_dir): p for p in pdfs}
        for i, fut in enumerate(as_completed(futures), 1):
            pdf = futures[fut]
            out_path, status = fut.result()
            if status == "ok":
                counts["ok"] += 1
            elif status == "cached":
                counts["cached"] += 1
            elif status.startswith("warn"):
                counts["warn"] += 1
                errors.append((pdf, status))
            else:
                counts["error"] += 1
                errors.append((pdf, status))

            if i % 50 == 0 or i == len(pdfs):
                elapsed = time.time() - started
                rate = i / elapsed if elapsed else 0
                eta = (len(pdfs) - i) / rate if rate else 0
                console.print(
                    f"  [{i:4d}/{len(pdfs)}] ok={counts['ok']} cached={counts['cached']} "
                    f"warn={counts['warn']} err={counts['error']} "
                    f"({rate:.1f}/s, ETA {eta:.0f}s)"
                )

    elapsed = time.time() - started
    console.print(f"\n[bold green]Done in {elapsed:.1f}s[/bold green]: {counts}")

    if errors:
        console.print(f"\n[yellow]{len(errors)} non-OK files:[/yellow]")
        for pdf, status in errors[:20]:
            console.print(f"  {pdf.name}  {status}")
        if len(errors) > 20:
            console.print(f"  ...and {len(errors) - 20} more")

    return 0 if counts["error"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
