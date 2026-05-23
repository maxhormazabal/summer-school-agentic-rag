from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

# Sample / lab dataset (3 example PDFs — used by Part 1 of the tutorial)
DOCS_DIR = DATA_DIR / "documents"
IMAGES_DIR = DATA_DIR / "images"
EXTRACTED_DIR = DATA_DIR / "extracted"

# Full official FCF dataset (1793 PDFs — used by Part 2 of the tutorial)
PDFS_FULL_DIR = DATA_DIR / "pages1793"
IMAGES_FULL_DIR = DATA_DIR / "images_full"
EXTRACTED_FULL_DIR = DATA_DIR / "extracted_full"

OUT_DIR = ROOT / "out"
TRACES_DIR = OUT_DIR / "agent_traces"
