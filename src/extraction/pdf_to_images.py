from __future__ import annotations

from pathlib import Path

from src.common.logging import console
from src.common.paths import DOCS_DIR, IMAGES_DIR


def convert(pdf_path: Path, dpi: int = 220) -> Path:
    """Convert a single-page PDF to PNG and return the output path."""
    from pdf2image import convert_from_path

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = IMAGES_DIR / (pdf_path.stem + ".png")
    if out_path.exists():
        console.print(f"[dim]Image cache hit: {out_path.name}[/dim]")
        return out_path

    pages = convert_from_path(str(pdf_path), dpi=dpi)
    pages[0].save(str(out_path), "PNG")
    console.print(f"[green]Converted {pdf_path.name} → {out_path.name}[/green]")
    return out_path


def convert_all(force: bool = False) -> list[Path]:
    """Convert all example PDFs; skip existing images unless force=True."""
    if force:
        for p in IMAGES_DIR.glob("example*.png"):
            p.unlink()

    return [convert(pdf) for pdf in sorted(DOCS_DIR.glob("example*.pdf"))]
