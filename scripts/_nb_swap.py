"""One-off: rewire the canonical notebook to use the full GDrive dataset (PLAN §11 data-swap).

In-place source replacement of specific cells (indices stable, no inserts/moves).
Run once: `./.venv/bin/python scripts/_nb_swap.py`.
"""
import json
from pathlib import Path

NB = Path("summer_school_document_agentic_rag_tutorial.ipynb")

MD = "markdown"
CODE = "code"

# --- new cell sources, keyed by index -------------------------------------------------
NEW = {}

NEW[10] = (CODE, '''\
# === Consolidated dataset download (1793 pre-computed FCF match reports) ===
# All 1793 official FCF reports were pre-processed on a GPU server with a local VLM
# (Qwen3-VL-8B-Instruct). Here we just download the artifacts — the page images (PNG)
# and the extracted JSON — and focus on the interesting parts.
import os, zipfile, subprocess, random
from pathlib import Path
from IPython.display import display, Image as IPImage
from src.common.paths import ROOT, IMAGES_FULL_DIR, EXTRACTED_FULL_DIR

PNG_ZIP_GDRIVE_ID  = "1FSBFc6nijVjApTh4YoP0seI8lOpBL6Xc"   # images_full.zip    (1793 PNG)
JSON_ZIP_GDRIVE_ID = "1GWH8lCd7TQV8g6N16intWJ5AFhpCU0FX"   # extracted_full.zip (1793 JSON)

def _download_and_unzip(gdrive_id, content_dir, min_files, label):
    """Download a zip from GDrive and unpack at repo ROOT (the archives carry
    `data/...` paths). Idempotent: skips if the content dir already holds enough files."""
    content_dir = Path(content_dir)
    n = sum(1 for p in content_dir.rglob("*") if p.is_file()) if content_dir.exists() else 0
    if n >= min_files:
        print(f"  {label}: already populated ({n} files), skipping download.")
        return
    zip_path = f"{label}.zip"
    subprocess.run(
        ["gdown", f"https://drive.google.com/uc?id={gdrive_id}", "-O", zip_path], check=True
    )
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(ROOT)  # paths: data/images_full/*.png and data/extracted_full/<tag>/*.json
    os.remove(zip_path)
    n = sum(1 for p in content_dir.rglob("*") if p.is_file())
    print(f"  {label}: downloaded and unpacked ({n} files).")

_download_and_unzip(PNG_ZIP_GDRIVE_ID,  IMAGES_FULL_DIR,    1500, "images_full")
_download_and_unzip(JSON_ZIP_GDRIVE_ID, EXTRACTED_FULL_DIR, 1500, "extracted_full")

# Preview one report page
pngs = sorted(IMAGES_FULL_DIR.glob("*.png"))
print(f"\\nDataset ready: {len(pngs)} match-report page images.")
sample_png = random.choice(pngs)
print(f"Preview: {sample_png.name}")
display(IPImage(str(sample_png), width=680))
''')

NEW[19] = (CODE, '''\
from src.common.paths import IMAGES_FULL_DIR

pngs = sorted(IMAGES_FULL_DIR.glob("*.png"))
print(f"{len(pngs)} page images already rendered from the source PDFs (220 DPI).")
print("No OCR is used — each image is fed to the VLM as raw pixels.")
''')

NEW[20] = (MD, '''\
### System prompt

The VLM receives a concise domain description in English that guides the knowledge extraction procedure. Let's look at it:

> ℹ️ The **bulk** run over all 1793 reports used a local **Qwen3-VL-8B-Instruct** model with this same prompt plus a short *SUPLENTS* (substitutes) emphasis — see `src/extraction/vlm_local.py`. The live demo below uses GPT-4o for illustration.
''')

NEW[22] = (MD, '''\
### Run extraction

The bulk extraction over all 1793 reports already ran on the GPU server. Below we run the VLM **live on a single page** so you can watch one extraction happen end-to-end.
''')

NEW[23] = (CODE, '''\
from src.extraction.vlm_extractor import extract
from src.common.paths import IMAGES_FULL_DIR, EXTRACTED_FULL_DIR

# The full dataset is already extracted (1793 JSONs downloaded above).
json_files = sorted(EXTRACTED_FULL_DIR.rglob("*.json"))
print(f"Pre-computed extractions available: {len(json_files)} JSON files.\\n")

# Live demo: run the VLM (GPT-4o) on ONE page image, right now, to see it work.
_preferred = ["10", "75", "17"]
sample_png = next(
    (IMAGES_FULL_DIR / f"{s}.png" for s in _preferred if (IMAGES_FULL_DIR / f"{s}.png").exists()),
    sorted(IMAGES_FULL_DIR.glob("*.png"))[0],
)
print(f"Live extraction demo on {sample_png.name} (1 OpenAI call)...")
demo = extract(sample_png)
print(f"  {demo.home.name} {demo.score_home}-{demo.score_away} {demo.away.name}  ·  J{demo.journey}")
print(f"  goals={len(demo.goals)}  cards={len(demo.cards)}  "
      f"lineup={len(demo.home.lineup)}+{len(demo.away.lineup)} players")
''')

NEW[24] = (MD, '''\
### Extracted data: sample review

Let's inspect a few extracted matches from the full dataset, side by side with their source page.
''')

NEW[25] = (CODE, '''\
import json
from PIL import Image
from IPython.display import display
from src.common.paths import IMAGES_FULL_DIR, EXTRACTED_FULL_DIR

# Bulk JSONs are model-namespaced: data/extracted_full/<model-tag>/*.json
_JSON_DIR = next(
    (d for d in sorted(EXTRACTED_FULL_DIR.iterdir()) if d.is_dir() and any(d.glob("*.json"))),
    EXTRACTED_FULL_DIR,
)

def show_match(stem: str):
    with Image.open(IMAGES_FULL_DIR / f"{stem}.png") as img:
        display(img.resize((int(img.width * 0.45), int(img.height * 0.45))))
    data = json.loads((_JSON_DIR / f"{stem}.json").read_text())

    print(f"\\n{'═'*60}")
    print(f"  {data['home']['name']}  {data['score_home']} – {data['score_away']}  {data['away']['name']}")
    print(f"  Journey {data['journey']} · {data['competition']} · {data['status']}")
    print(f"  Stadium : {data['stadium']['name']}")
    print(f"  Referee : {data['referee']['name']} ({data['referee'].get('committee','')})")
    print(f"{'─'*60}")
    print(f"  Goals ({len(data['goals'])})")
    for g in data['goals']:
        icon = "⚽" if g['type'] == 'regular' else ("🔄" if g['type'] == 'own' else "⚡")
        print(f"    {icon} {g['minute']:>3}' {g['scorer_name']}  ({g['scoreline_home']}-{g['scoreline_away']})")
    if data['cards']:
        print(f"  Cards ({len(data['cards'])})")
        for c in data['cards']:
            print(f"    {c['color']:>6} {c['minute']:>3}' {c['target_name']} [{c['target_kind']}]")
''')

NEW[26] = (CODE, '''\
print("\\n" + "▶" * 3 + "  SAMPLE MATCH A  " + "◀" * 3)
show_match("10")
''')

NEW[27] = (CODE, '''\
print("\\n" + "▶" * 3 + "  SAMPLE MATCH B  " + "◀" * 3)
show_match("75")
''')

NEW[29] = (CODE, '''\
from src.common.ids import normalize_name
from src.common.paths import EXTRACTED_FULL_DIR
from src.ontology.schema import MatchExtraction
from rich.table import Table
from rich.console import Console

_JSON_DIR = next(
    (d for d in sorted(EXTRACTED_FULL_DIR.iterdir()) if d.is_dir() and any(d.glob("*.json"))),
    EXTRACTED_FULL_DIR,
)

table = Table(title="Extraction Quality (sample of 8)")
table.add_column("File", style="bold")
table.add_column("Match")
table.add_column("Goals = score", justify="center")
table.add_column("Scorers in lineup", justify="center")
table.add_column("Coach cards", justify="center")

for json_path in sorted(_JSON_DIR.glob("*.json"))[:8]:
    m = MatchExtraction.model_validate_json(json_path.read_text(encoding="utf-8"))
    all_players = {normalize_name(e.player.name) for e in m.home.lineup + m.away.lineup}
    goals_ok = len(m.goals) == m.score_home + m.score_away
    scorers_ok = all(normalize_name(g.scorer_name) in all_players for g in m.goals)
    coach_cards = sum(1 for c in m.cards if c.target_kind.value == "coach")
    table.add_row(
        json_path.name,
        f"{m.home.name} {m.score_home}-{m.score_away} {m.away.name}",
        "✅" if goals_ok else "❌",
        "✅" if scorers_ok else "❌",
        str(coach_cards) if coach_cards else "—",
    )

Console().print(table)
''')

NEW[34] = (CODE, '''\
from src.graph.ingest import ingest_full

# Reads data/extracted_full/<model-tag>/*.json and MERGEs everything into Neo4j.
# This ingests all ~1793 reports — expect a few minutes on AuraDB Free.
counts = ingest_full()
''')

NEW[35] = (CODE, '''\
from rich.table import Table
from rich.console import Console

table = Table(title="Node counts after ingestion")
table.add_column("Label", style="bold cyan")
table.add_column("Count", justify="right")
for label, count in sorted(counts.items()):
    table.add_row(label, str(count))
Console().print(table)

# Soft sanity checks (full dataset — exact totals depend on the data).
print(f"\\nMatches ingested: {counts.get('Match', 0)}")
assert counts.get("Match", 0) > 0 and counts.get("Goal", 0) > 0, \\
    "Graph looks empty — check the download and ingest steps."
print("✅ Graph populated.")
''')

NEW[36] = (MD, '''\
### Idempotency test

The ingestion is built on `MERGE`, so re-ingesting reports that are already in the graph
must **not** change any counts. Re-running the full 1793 would be slow, so we re-ingest a
small sample and confirm the totals are unchanged.
''')

NEW[37] = (CODE, '''\
from src.graph.ingest import ingest_match
from src.graph.neo4j_client import Neo4jClient
from src.ontology.schema import MatchExtraction
from src.common.paths import EXTRACTED_FULL_DIR

_JSON_DIR = next(
    (d for d in sorted(EXTRACTED_FULL_DIR.iterdir()) if d.is_dir() and any(d.glob("*.json"))),
    EXTRACTED_FULL_DIR,
)
sample = sorted(_JSON_DIR.glob("*.json"))[:20]
print(f"Re-ingesting {len(sample)} already-loaded reports to test idempotency...")
for jf in sample:
    ingest_match(MatchExtraction.model_validate_json(jf.read_text(encoding="utf-8")))

counts2 = {}
with Neo4jClient() as client:
    for label in ["Match", "Team", "Player", "Coach", "Stadium", "Referee", "Goal", "Card"]:
        r = client.run_read(f"MATCH (n:{label}) RETURN count(n) AS c")
        counts2[label] = r[0]["c"] if r else 0

assert counts2 == counts, f"Idempotency failed!\\nBefore: {counts}\\nAfter:  {counts2}"
print("✅ Idempotency confirmed — counts unchanged after re-ingesting a sample.")
''')

# --- apply ----------------------------------------------------------------------------
nb = json.loads(NB.read_text(encoding="utf-8"))
cells = nb["cells"]
for idx, (ctype, src) in NEW.items():
    cell = cells[idx]
    assert cell["cell_type"] == ctype, f"cell {idx}: expected {ctype}, got {cell['cell_type']}"
    cell["source"] = src.splitlines(keepends=True)
    if ctype == CODE:
        cell["outputs"] = []
        cell["execution_count"] = None

NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"Patched {len(NEW)} cells: {sorted(NEW)}")
