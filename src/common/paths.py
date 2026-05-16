from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
EXAMPLES_DIR = DATA_DIR / "examples"
IMAGES_DIR = DATA_DIR / "images"
EXTRACTED_DIR = DATA_DIR / "extracted"
OUT_DIR = ROOT / "out"
TRACES_DIR = OUT_DIR / "agent_traces"
