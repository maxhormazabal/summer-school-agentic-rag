from __future__ import annotations

import json
from pathlib import Path

from src.common.logging import console
from src.common.paths import DOCS_DIR, EXTRACTED_DIR, IMAGES_DIR
from src.extraction.pdf_to_images import convert
from src.extraction.vlm_extractor import extract
from src.ontology.schema import MatchExtraction


def run(force: bool = False) -> list[Path]:
    """Extract all example PDFs → JSON. Skips existing JSONs unless force=True."""
    EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    for pdf_path in sorted(DOCS_DIR.glob("example*.pdf")):
        json_path = EXTRACTED_DIR / (pdf_path.stem + ".json")

        if json_path.exists() and not force:
            console.print(f"[dim]Extraction cache hit: {json_path.name}[/dim]")
            results.append(json_path)
            continue

        img_path = convert(pdf_path, dpi=220)
        match = extract(img_path)

        # soft validation
        expected = match.score_home + match.score_away
        actual = len(match.goals)
        if expected != actual:
            console.print(
                f"[yellow]Warning ({pdf_path.name}): score_home+score_away={expected} "
                f"but len(goals)={actual}[/yellow]"
            )

        json_path.write_text(
            match.model_dump_json(indent=2), encoding="utf-8"
        )
        console.print(f"[green]Saved {json_path.name}[/green]")
        results.append(json_path)

    return results


def inspect(n: int) -> tuple:
    """Return (PIL.Image, dict) for example N (1-indexed) for inline display."""
    from PIL import Image as PILImage

    img_path = IMAGES_DIR / f"example{n}.png"
    json_path = EXTRACTED_DIR / f"example{n}.json"

    if not img_path.exists():
        pdf_path = DOCS_DIR / f"example{n}.pdf"
        img_path = convert(pdf_path)

    img = PILImage.open(img_path)
    data = json.loads(json_path.read_text(encoding="utf-8")) if json_path.exists() else {}
    return img, data
