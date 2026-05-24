"""One-off builder for the Qwen3.5-in-Colab notebooks.

Emits two notebooks from a single source of truth:

* ``summer_school_document_agentic_rag_tutorial.ipynb`` — canonical tutorial,
  Part 1 (interactive lab, exercises blank) + Part 2 (at scale).
* ``summer_school_part1_solutions.ipynb`` — Part 1 only, every exercise solved.

Design (per the 2026-05-24 rewrite request):
* No OpenAI, no remote vLLM. Two GGUF models are loaded *in Colab* via a
  ``llama-server`` subprocess exposing an OpenAI-compatible ``/v1`` endpoint, which
  the existing ``local`` backend in ``src/common/llm.py`` points at.
    - extraction (vision): ``unsloth/Qwen3.5-4B-GGUF`` + ``mmproj-F16.gguf``
    - agent (tool-calls):  ``unsloth/Qwen3.5-2B-GGUF`` (``--jinja``)
* All downloads (llama.cpp build, both GGUFs, the 1793 GDrive dataset) happen once,
  up front in the Setup section.
* The vision model is unloaded (server killed → VRAM freed) before the agent model
  is loaded, so a small Colab GPU never holds both at once.

Run:  ./.venv/bin/python scripts/_build_qwen_notebooks.py
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "summer_school_document_agentic_rag_tutorial.ipynb"
SOLUTIONS = ROOT / "summer_school_part1_solutions.ipynb"

NB_METADATA = {
    "colab": {"provenance": []},
    "kernelspec": {"display_name": ".venv", "language": "python", "name": "python3"},
    "language_info": {
        "codemirror_mode": {"name": "ipython", "version": 3},
        "file_extension": ".py",
        "mimetype": "text/x-python",
        "name": "python",
        "nbconvert_exporter": "python",
        "pygments_lexer": "ipython3",
        "version": "3.11.3",
    },
}


def _cell_id() -> str:
    return uuid.uuid4().hex[:8]


def md(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "id": _cell_id(),
        "source": source.strip("\n").splitlines(keepends=True),
    }


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "metadata": {},
        "id": _cell_id(),
        "execution_count": None,
        "outputs": [],
        "source": source.strip("\n").splitlines(keepends=True),
    }


# ════════════════════════════════════════════════════════════════════════════
# Header
# ════════════════════════════════════════════════════════════════════════════
def header_cells() -> list[dict]:
    return [
        md(
            """
<div align="center">
  <img src="https://raw.githubusercontent.com/maxhormazabal/summer-school-agentic-rag/refs/heads/main/tutorial_imgs/logo_red.svg" alt="Summer School DAG Logo" width="200"/>
</div>

# Agentic RAG with Vision AI & Knowledge Graphs

We build an end-to-end **Agentic RAG** system over a knowledge graph populated from PDF match
reports using vision AI — in two parts:

- **Part 1 — Interactive Lab.** A small, controlled setting (3 reports) where *you* complete the
  code for each phase: ontology, extraction checks, graph queries, and the agent.
- **Part 2 — At Scale.** The same pipeline running over the full official dataset of **1793**
  reports, with extraction already pre-computed.

Both models run **inside this Colab** as open-weight **Qwen3.5** GGUFs (no API keys, no OpenAI):
a 4B vision model reads the report images, and a 2B model drives the agent.

| Stage | What happens |
|---|---|
| **1 — Ontology** | Define the domain as Pydantic models |
| **2 — VLM Extraction** | Qwen3.5-4B (vision) reads PDF pages → structured JSON |
| **3 — Knowledge Graph** | JSON → Neo4J nodes & relationships (MERGE, idempotent) |
| **4 — Agentic RAG** | Natural language → Cypher → answer via tool-calling (Qwen3.5-2B) |
"""
        ),
        code(
            """
import base64
import requests, io
from IPython.display import SVG, display

graph = \"\"\"
flowchart LR
    A[PDF] --> B["Vision Language Model"]
    B --> C["Structured JSON<br/>(Pydantic)"]
    C --> D["Neo4J Graph<br/>(MERGE)"]
    D --> E[Agent]
    E --> F[Answer]
\"\"\"

graphbytes = graph.encode("ascii")
base64_bytes = base64.b64encode(graphbytes)
base64_string = base64_bytes.decode("ascii")
url = f"https://mermaid.ink/svg/{base64_string}"

svg_data = requests.get(url).text

display(SVG(svg_data))
"""
        ),
        md(
            """
> **Domain:** Official match reports (*actes*) from the Federació Catalana de Futbol (FCF), written in Catalan.
"""
        ),
    ]


# ════════════════════════════════════════════════════════════════════════════
# Setup (shared by both parts and both notebooks)
# ════════════════════════════════════════════════════════════════════════════
def setup_cells() -> list[dict]:
    return [
        md(
            """
## 0 · Setup

Credentials, models, dependencies, connectivity — shared by both parts.

> ⏳ **This section does a one-time heavy setup** (~10 min on a fresh Colab): it builds
> `llama.cpp` with CUDA, downloads two Qwen3.5 GGUF models (~4 GB), and downloads the
> 1793-report dataset for Part 2. Run it once and grab a coffee — later cells are fast.
> **Use a GPU runtime** (Runtime → Change runtime type → T4 GPU).
"""
        ),
        md(
            """
### Credentials

You only need a free **Neo4J AuraDB** instance ([console.neo4j.io](https://console.neo4j.io)).
No OpenAI key — the models run locally in this notebook.
"""
        ),
        code(
            """
import os

# ── Paste your Neo4J credentials here ─────────────────────────────────────────
NEO4J_URI='<paste-your-neo4j-uri>'         # e.g. neo4j+s://<id>.databases.neo4j.io
NEO4J_USERNAME='<paste-your-neo4j-user>'   # default: neo4j
NEO4J_PASSWORD='<paste-your-neo4j-password>'
NEO4J_DATABASE='<paste-your-neo4j-database>'  # default: neo4j
# ──────────────────────────────────────────────────────────────────────────────

os.environ["NEO4J_URI"]      = NEO4J_URI
os.environ["NEO4J_USERNAME"] = NEO4J_USERNAME
os.environ["NEO4J_PASSWORD"] = NEO4J_PASSWORD
os.environ["NEO4J_DATABASE"] = NEO4J_DATABASE

print("Credentials set ✓")
"""
        ),
        md(
            """
### Models — two Qwen3.5 GGUFs, loaded in Colab

This system is **backend-agnostic**; here both roles use the `"local"` backend pointed at a
`llama-server` we launch inside this notebook (OpenAI-compatible `/v1` endpoint).

| Role | Model | Why |
|---|---|---|
| **Extraction** | `Qwen3.5-4B` + vision projector | Reads the report image → JSON. Needs vision. |
| **Agent** | `Qwen3.5-2B` | Turns questions into Cypher via tool-calls. Light & fast. |

> 🧠 **One model at a time.** Colab's GPU is small, so we load the 4B vision model for
> extraction, then **unload it** (free the VRAM) before loading the 2B agent model. The
> swap happens automatically between Part 1's extraction and graph sections.
"""
        ),
        code(
            """
# ── In-Colab model choice (Qwen3.5 GGUF via llama.cpp) ────────────────────────
EXTRACTION_REPO  = "unsloth/Qwen3.5-4B-GGUF"   # vision: report image → JSON
EXTRACTION_QUANT = "UD-Q4_K_XL"
AGENT_REPO       = "unsloth/Qwen3.5-2B-GGUF"   # text:   question → Cypher (tool-calls)
AGENT_QUANT      = "UD-Q4_K_XL"

LLAMA_PORT     = 8000
LOCAL_BASE_URL = f"http://127.0.0.1:{LLAMA_PORT}/v1"

# Both roles talk to the same local server (one model loaded at a time — we swap them).
os.environ["EXTRACTION_BACKEND"]  = "local"
os.environ["AGENT_BACKEND"]       = "local"
os.environ["LOCAL_VLLM_BASE_URL"] = LOCAL_BASE_URL
os.environ["LOCAL_VLLM_MODEL"]    = "qwen"          # alias; llama-server serves whatever is loaded
os.environ["LOCAL_VLLM_API_KEY"]  = "sk-no-key-required"

print(f"Extraction → local · {EXTRACTION_REPO}:{EXTRACTION_QUANT}")
print(f"Agent      → local · {AGENT_REPO}:{AGENT_QUANT}")
"""
        ),
        code(
            """
import sys, os, subprocess

# ── Environment detection ─────────────────────────────────────────────────────
try:
    from google.colab import userdata  # noqa: F401
    IN_COLAB = True
except ImportError:
    IN_COLAB = False

COLAB_SIMULATE = os.environ.get("COLAB_SIMULATE", "").lower() in ("1", "true")
GITHUB_REPO_URL = "https://github.com/maxhormazabal/summer-school-agentic-rag.git"

if IN_COLAB:
    REPO_NAME = GITHUB_REPO_URL.rsplit("/", 1)[-1].removesuffix(".git")
    if not os.path.isdir(REPO_NAME):
        subprocess.run(["git", "clone", "--depth", "1", GITHUB_REPO_URL], check=True)
    os.chdir(REPO_NAME)
    # System dependencies: poppler/graphviz for the pipeline, build tools for llama.cpp.
    subprocess.run(
        ["apt-get", "install", "-y", "-q", "poppler-utils", "graphviz",
         "build-essential", "cmake", "curl", "libcurl4-openssl-dev"],
        capture_output=True, check=True,
    )
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                    "huggingface_hub", "hf_transfer", "gdown", "openai"], check=True)
elif COLAB_SIMULATE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)

REPO_ROOT = os.path.abspath(".")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

mode = "Google Colab" if IN_COLAB else ("Colab Simulation" if COLAB_SIMULATE else "Local Dev")
print(f"Environment : {mode}")
print(f"Repo root   : {REPO_ROOT}")
"""
        ),
        md(
            """
### Build `llama.cpp` + download the models (one-time)

We build `llama.cpp` with CUDA so a single binary can serve **both** vision and text models
with an OpenAI-compatible API. Then we pull the two Qwen3.5 GGUFs from Hugging Face. Both the
build and the downloads are cached — re-running this cell is instant.
"""
        ),
        code(
            """
import os, subprocess
from pathlib import Path
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"

# 0. Fail fast if there's no GPU — the CUDA build takes ~10 min and is useless on CPU.
assert subprocess.run(["nvidia-smi"], capture_output=True).returncode == 0, \\
    "No GPU detected. In Colab: Runtime → Change runtime type → T4 GPU, then re-run."

# 1. Build llama.cpp with CUDA (≈8–12 min the first time; skipped if already built).
LLAMA_BIN = Path("llama.cpp/build/bin/llama-server")
if not LLAMA_BIN.exists():
    if not Path("llama.cpp").exists():
        subprocess.run(["git", "clone", "--depth", "1",
                        "https://github.com/ggml-org/llama.cpp"], check=True)
    subprocess.run(["cmake", "-S", "llama.cpp", "-B", "llama.cpp/build",
                    "-DGGML_CUDA=ON", "-DLLAMA_CURL=ON", "-DLLAMA_BUILD_TESTS=OFF"], check=True)
    subprocess.run(["cmake", "--build", "llama.cpp/build", "--config", "Release", "-j",
                    "--target", "llama-server", "llama-mtmd-cli"], check=True)
LLAMA_BIN = str(LLAMA_BIN)
print("llama-server :", LLAMA_BIN)

# 2. Download the two GGUFs (the 4B also needs its vision projector, mmproj).
from huggingface_hub import snapshot_download

def _fetch_gguf(repo, quant, want_mmproj):
    patterns = [f"*{quant}.gguf"] + (["*mmproj-F16.gguf"] if want_mmproj else [])
    d = Path(snapshot_download(repo, allow_patterns=patterns))
    model  = next(p for p in d.glob("*.gguf") if "mmproj" not in p.name.lower())
    mmproj = next((p for p in d.glob("*mmproj*.gguf")), None)
    return str(model), (str(mmproj) if mmproj else None)

EXTRACTION_MODEL_PATH, EXTRACTION_MMPROJ = _fetch_gguf(EXTRACTION_REPO, EXTRACTION_QUANT, True)
AGENT_MODEL_PATH, _                      = _fetch_gguf(AGENT_REPO,      AGENT_QUANT,      False)
print("Extraction   :", Path(EXTRACTION_MODEL_PATH).name, "+", Path(EXTRACTION_MMPROJ).name)
print("Agent        :", Path(AGENT_MODEL_PATH).name)
"""
        ),
        md(
            """
### Download the Part 2 dataset (1793 reports)

We pull the page images and the pre-computed extractions now so everything is ready before we
start. Part 1 uses the 3 reports already in the repo, so it doesn't depend on this download.
"""
        ),
        code(
            """
# === Consolidated dataset download (1793 pre-computed FCF match reports) ===
# Pre-processed on a GPU server with Qwen3-VL; here we just fetch the artifacts:
# the page images (PNG) and the extracted JSON.
import os, zipfile, subprocess
from pathlib import Path
from src.common.paths import ROOT, IMAGES_FULL_DIR, EXTRACTED_FULL_DIR

PNG_ZIP_GDRIVE_ID  = "1FSBFc6nijVjApTh4YoP0seI8lOpBL6Xc"   # images_full.zip    (1793 PNG)
JSON_ZIP_GDRIVE_ID = "1GWH8lCd7TQV8g6N16intWJ5AFhpCU0FX"   # extracted_full.zip (1793 JSON)

def _download_and_unzip(gdrive_id, content_dir, min_files, label):
    \"\"\"Download a zip from GDrive and unpack at repo ROOT (archives carry `data/...` paths).
    Idempotent: skips if the content dir already holds enough files.\"\"\"
    content_dir = Path(content_dir)
    n = sum(1 for p in content_dir.rglob("*") if p.is_file()) if content_dir.exists() else 0
    if n >= min_files:
        print(f"  {label}: already populated ({n} files), skipping download.")
        return
    zip_path = f"{label}.zip"
    subprocess.run(["gdown", f"https://drive.google.com/uc?id={gdrive_id}", "-O", zip_path], check=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(ROOT)
    os.remove(zip_path)
    n = sum(1 for p in content_dir.rglob("*") if p.is_file())
    print(f"  {label}: downloaded and unpacked ({n} files).")

_download_and_unzip(PNG_ZIP_GDRIVE_ID,  IMAGES_FULL_DIR,    1500, "images_full")
_download_and_unzip(JSON_ZIP_GDRIVE_ID, EXTRACTED_FULL_DIR, 1500, "extracted_full")
print("\\nDataset ready for Part 2.")
"""
        ),
        md(
            """
### The model server (load / unload helpers)

`start_llama_server(...)` (re)starts `llama-server` with one model and blocks until its `/v1`
endpoint answers; `stop_llama_server()` kills it and frees the GPU. Starting a new server
always stops the previous one first — that's how we swap vision → agent without running out
of VRAM.
"""
        ),
        code(
            """
import subprocess, time, requests
from pathlib import Path

Path("out").mkdir(exist_ok=True)
_LLAMA_PROC = None

def stop_llama_server():
    \"\"\"Kill any running llama-server and free its GPU memory.\"\"\"
    global _LLAMA_PROC
    subprocess.run(["pkill", "-9", "-f", "llama-server"], check=False)
    _LLAMA_PROC = None
    time.sleep(3)

def start_llama_server(model_path, mmproj=None, jinja=False, ctx=16384,
                       alias="qwen", port=LLAMA_PORT, ngl=999):
    \"\"\"(Re)start llama-server with a single model; block until /v1 is ready.\"\"\"
    global _LLAMA_PROC
    stop_llama_server()  # free VRAM from any previous model first
    cmd = [LLAMA_BIN, "--model", model_path, "--alias", alias,
           "--host", "127.0.0.1", "--port", str(port),
           "--n-gpu-layers", str(ngl), "--ctx-size", str(ctx)]
    if mmproj:
        cmd += ["--mmproj", mmproj]
    if jinja:
        cmd += ["--jinja"]          # enables OpenAI-style tool-calling for Qwen
    logf = open("out/llama_server.log", "w")
    _LLAMA_PROC = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT)

    url = f"http://127.0.0.1:{port}/v1/models"
    for _ in range(180):            # up to ~6 min for the first model load
        if _LLAMA_PROC.poll() is not None:
            raise RuntimeError("llama-server exited during startup — see out/llama_server.log")
        try:
            if requests.get(url, timeout=2).status_code == 200:
                tag = Path(model_path).name + (f" + {Path(mmproj).name}" if mmproj else "")
                print(f"✓ llama-server ready: {tag}" + ("  [tool-calls]" if jinja else ""))
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise TimeoutError("llama-server did not become ready in time — see out/llama_server.log")

print("Helpers ready: start_llama_server(), stop_llama_server()")
"""
        ),
        md(
            """
### Connectivity check

The model servers start on demand later; here we just confirm Neo4J is reachable.
"""
        ),
        code(
            """
from rich.table import Table
from rich.console import Console
from src.graph.neo4j_client import Neo4jClient

def neo4j_check() -> bool:
    t = Table(title="Connectivity")
    for col in ("Service", "Status", "Detail"):
        t.add_column(col)
    try:
        with Neo4jClient() as c:
            c.run_read("RETURN 1 AS x")
        t.add_row("Neo4J", "✅", "OK")
        ok = True
    except Exception as e:
        t.add_row("Neo4J", "❌", str(e)[:70])
        ok = False
    Console().print(t)
    return ok

assert neo4j_check(), "Fix Neo4J connectivity before continuing."
"""
        ),
    ]


# ════════════════════════════════════════════════════════════════════════════
# Part 1 — interactive lab. `solved=True` fills in the exercise answers.
# ════════════════════════════════════════════════════════════════════════════
def part1_cells(solved: bool) -> list[dict]:
    # ---- exercise 1: Goal model ----------------------------------------------
    goal_skeleton = """
from pydantic import BaseModel
from typing import Literal
from src.ontology.schema import GoalType   # provided enum: regular | own | penalty

class MyGoal(BaseModel):
    # 📝 TODO: declare the six fields described in the table above.
    # Example syntax:  minute: int
    ...
"""
    goal_solution = """
from pydantic import BaseModel
from typing import Literal
from src.ontology.schema import GoalType   # provided enum: regular | own | penalty

class MyGoal(BaseModel):
    minute: int
    scoreline_home: int
    scoreline_away: int
    scorer_name: str
    scoring_team: Literal["home", "away"]
    type: GoalType
"""

    # ---- exercise 2: quality_check -------------------------------------------
    quality_skeleton = """
from src.common.ids import normalize_name
from src.ontology.schema import MatchExtraction

def quality_check(m: MatchExtraction) -> dict:
    # 📝 TODO: return {"goals_ok": <bool>, "scorers_ok": <bool>}
    # Hint: build a set of normalised player names from both lineups, then test each scorer.
    ...
"""
    quality_solution = """
from src.common.ids import normalize_name
from src.ontology.schema import MatchExtraction

def quality_check(m: MatchExtraction) -> dict:
    names = {normalize_name(e.player.name) for e in (m.home.lineup + m.away.lineup)}
    goals_ok = len(m.goals) == m.score_home + m.score_away
    scorers_ok = all(normalize_name(g.scorer_name) in names for g in m.goals)
    return {"goals_ok": goals_ok, "scorers_ok": scorers_ok}
"""

    # ---- exercise 3: Cypher goals-per-team -----------------------------------
    cypher_skeleton = """
from src.agent.tools import run_cypher

cypher = \"\"\"
MATCH (g:Goal)-[:FOR_TEAM]->(t:Team)
RETURN t.name AS team, ___ AS goals
ORDER BY goals DESC
\"\"\"

result = run_cypher(cypher)
print(result)
"""
    cypher_solution = """
from src.agent.tools import run_cypher

cypher = \"\"\"
MATCH (g:Goal)-[:FOR_TEAM]->(t:Team)
RETURN t.name AS team, count(g) AS goals
ORDER BY goals DESC
\"\"\"

result = run_cypher(cypher)
print(result)
"""

    # ---- exercise 4a: own question -------------------------------------------
    question_skeleton = """
MY_QUESTION = "Which team scored the most goals?"   # 📝 TODO: change this

result = ask(MY_QUESTION)
print("\\nAnswer:", result.answer)
"""
    question_solution = """
MY_QUESTION = "Who scored in the match between Cirera and L'Estartit, and in which minute?"

result = ask(MY_QUESTION)
print("\\nAnswer:", result.answer)
"""

    # ---- exercise 4b: tone ----------------------------------------------------
    tone_skeleton = """
from src.agent import prompts

TONE_INSTRUCTION = "Answer in a very formal, ceremonious tone."   # 📝 TODO: change this

# Capture the base prompt once so re-running this cell with a new tone doesn't stack rules.
if not hasattr(prompts, "_BASE_SYSTEM_PROMPT"):
    prompts._BASE_SYSTEM_PROMPT = prompts.SYSTEM_PROMPT
prompts.SYSTEM_PROMPT = prompts._BASE_SYSTEM_PROMPT + "\\n\\nADDITIONAL STYLE RULE: " + TONE_INSTRUCTION

result = ask("What was the score between Cirera and L'Estartit?")
print("\\nAnswer:", result.answer)
"""
    tone_solution = """
from src.agent import prompts

TONE_INSTRUCTION = "Always answer in Catalan, in a friendly and concise tone."

# Capture the base prompt once so re-running this cell with a new tone doesn't stack rules.
if not hasattr(prompts, "_BASE_SYSTEM_PROMPT"):
    prompts._BASE_SYSTEM_PROMPT = prompts.SYSTEM_PROMPT
prompts.SYSTEM_PROMPT = prompts._BASE_SYSTEM_PROMPT + "\\n\\nADDITIONAL STYLE RULE: " + TONE_INSTRUCTION

result = ask("What was the score between Cirera and L'Estartit?")
print("\\nAnswer:", result.answer)
"""

    pick = lambda skel, sol: sol if solved else skel

    cells = [
        md(
            """
---
# Part 1 — Interactive Lab

Hands-on with **3 sample match reports** — small enough to *touch things* and see what happens.

> ⚠️ **How to use Part 1**
> - Edit **only** the cells marked **📝 Your turn**. Everything else is scaffolding.
> - Each 📝 exercise is followed by a **✅ / ❌ check** cell.
> - Broke something? **Re-run from the top.** Nothing here is destructive.

Part 1 uses the 3 reports shipped in the repo (`data/`), so no extra download is needed.
"""
        ),
        # 1 · domain
        md(
            """
## 1 · The domain — FCF match reports

Each report is a single PDF page (in Catalan) containing the lineups (**TITULARS** / **SUPLENTS**),
technical staff, goals (**GOLS**), cards (**TARGETES**), stadium and referee. The VLM reads the
**image** — no OCR. Let's look at one.
"""
        ),
        code(
            """
from pdf2image import convert_from_path
from IPython.display import display
from src.common.paths import DOCS_DIR

page = convert_from_path(str(DOCS_DIR / "example1.pdf"), dpi=110, first_page=1, last_page=1)[0]
display(page.resize((int(page.width * 0.6), int(page.height * 0.6))))
"""
        ),
        # 2 · ontology
        md(
            """
## 2 · Ontology

The ontology is just a set of **Pydantic models** describing what a match report contains.
`MatchExtraction` is the root; it nests `Team`, `Player`, `Goal`, `Card`, `Stadium`, `Referee`.
Here is the diagram:
"""
        ),
        code(
            """
from src.ontology.visualize import render_ontology
render_ontology()   # writes out/ontology.png and returns a displayable diagram
"""
        ),
        md(
            """
### 📝 Your turn — complete the `Goal` model

A goal in the report has a minute, the running scoreline, who scored, which side scored, and
its type. **Fill in the fields** of `MyGoal` below to match this spec:

| field | type |
|---|---|
| `minute` | `int` |
| `scoreline_home` | `int` |
| `scoreline_away` | `int` |
| `scorer_name` | `str` |
| `scoring_team` | `Literal["home", "away"]` |
| `type` | `GoalType` (enum: `regular` / `own` / `penalty`) |
"""
        ),
        code(pick(goal_skeleton, goal_solution)),
        code(
            """
# ✅ check
expected = {"minute", "scoreline_home", "scoreline_away", "scorer_name", "scoring_team", "type"}
sample = {"minute": 23, "scoreline_home": 1, "scoreline_away": 0,
          "scorer_name": "PUIG, ANNA", "scoring_team": "home", "type": "regular"}
try:
    g = MyGoal(**sample)
    got = set(MyGoal.model_fields)
    assert got == expected, f"Fields differ.\\n  expected: {expected}\\n  got:      {got}"
    assert g.type == GoalType.regular and g.scoring_team == "home"
    print("✅ Your Goal model has exactly the right fields and validates the sample.")
except Exception as e:
    print("❌", type(e).__name__, "-", e)
"""
        ),
        # 3 · extraction — load vision model
        md(
            """
## 3 · Extraction (VLM → JSON)

Time to load the **vision model**. We start `llama-server` with **Qwen3.5-4B + its vision
projector** — this is the model that reads a report image and returns JSON.
"""
        ),
        code(
            """
# Load the VISION model (Qwen3.5-4B). Frees any previously loaded model first.
start_llama_server(EXTRACTION_MODEL_PATH, mmproj=EXTRACTION_MMPROJ, ctx=16384)
"""
        ),
        md(
            """
The VLM receives the page image plus this domain prompt and must return JSON validated against
the ontology:
"""
        ),
        code(
            """
from src.extraction.vlm_extractor import _SYSTEM_PROMPT
print(_SYSTEM_PROMPT)
"""
        ),
        md(
            """
Now run extraction **live** on all 3 sample reports. Each call sends the page image to
Qwen3.5-4B and validates the JSON against the ontology (with a retry on failure). Results are
written to `data/extracted/` and feed the graph below.
"""
        ),
        code(
            """
from pathlib import Path
from src.extraction.pdf_to_images import convert_all
from src.extraction.vlm_extractor import extract
from src.common.paths import IMAGES_DIR, EXTRACTED_DIR
from src.ontology.schema import MatchExtraction

convert_all()                       # data/documents/example*.pdf → data/images/example*.png
EXTRACTED_DIR.mkdir(parents=True, exist_ok=True)

for png in sorted(IMAGES_DIR.glob("example*.png")):
    try:
        m = extract(png)
        (EXTRACTED_DIR / f"{png.stem}.json").write_text(
            m.model_dump_json(indent=2), encoding="utf-8")
        print(f"  {png.name}: {m.home.name} {m.score_home}-{m.score_away} {m.away.name}"
              f" · goals={len(m.goals)}")
    except Exception as e:
        print(f"  {png.name}: extraction failed ({type(e).__name__}) — keeping any cached JSON.")
"""
        ),
        md(
            """
### 📝 Your turn — write a data-quality check

When you extract data automatically, you need cheap checks that it isn't hallucinated. Implement
`quality_check(m)` returning a dict with two booleans:

- **`goals_ok`** — the number of goals equals the final score: `len(m.goals) == m.score_home + m.score_away`
- **`scorers_ok`** — every goal's scorer appears in *some* lineup, after name normalisation.

Helpers: `normalize_name(text)`; lineups are `m.home.lineup` / `m.away.lineup`; each entry has
`entry.player.name`.
"""
        ),
        code(pick(quality_skeleton, quality_solution)),
        code(
            """
# ✅ check — runs your function over the 3 extracted reports
from pathlib import Path
from src.common.paths import EXTRACTED_DIR

all_ok = True
files = sorted(EXTRACTED_DIR.glob("example*.json"))
for f in files:
    m = MatchExtraction.model_validate_json(f.read_text(encoding="utf-8"))
    r = quality_check(m) or {}
    print(f"  {f.name}: goals_ok={r.get('goals_ok')}  scorers_ok={r.get('scorers_ok')}")
    all_ok = all_ok and bool(r.get("goals_ok")) and bool(r.get("scorers_ok"))
print("✅ quality_check passes on all reports." if (files and all_ok)
      else "❌ Not all checks pass — review your quality_check (or the live extraction above).")
"""
        ),
        # unload vision → load agent
        md(
            """
### Swap models: unload vision, load the agent

Extraction is done, so we **unload the 4B vision model** to free GPU memory, then load the
**2B agent model** (with `--jinja` for tool-calling). Watch the VRAM drop and rise.
"""
        ),
        code(
            """
# Free the vision model's VRAM and confirm the GPU is (almost) empty.
stop_llama_server()
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                      "--format=csv,noheader"], capture_output=True, text=True).stdout or "(no GPU)")
"""
        ),
        code(
            """
# Load the AGENT model (Qwen3.5-2B) with tool-calling enabled.
start_llama_server(AGENT_MODEL_PATH, jinja=True, ctx=16384)
import subprocess
print(subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.total",
                      "--format=csv,noheader"], capture_output=True, text=True).stdout or "(no GPU)")
"""
        ),
        # 4 · graph
        md(
            """
## 4 · The knowledge graph

We turn the JSON into Neo4J nodes and relationships. Ingestion uses `MERGE`, so it is
**idempotent** — running it twice doesn't duplicate anything. Let's load the 3 reports.
"""
        ),
        code(
            """
from src.graph.constraints import apply as apply_constraints
from src.graph.ingest import ingest_all

apply_constraints()
counts = ingest_all()   # ingests the 3 reports from data/extracted/
print("Node counts:", counts)
"""
        ),
        md(
            """
### 📝 Your turn — count goals per team in Cypher

The graph has `(Goal)-[:FOR_TEAM]->(Team)` and every `Team` has a `name` property. **Complete
the query** so it returns one row per team with its goal count. Replace `___` with the right
aggregation.
"""
        ),
        code(pick(cypher_skeleton, cypher_solution)),
        code(
            """
# ✅ check — compares your query against the count computed in Python from the JSONs
from collections import Counter
from src.common.paths import EXTRACTED_DIR

expected = Counter()
for f in sorted(EXTRACTED_DIR.glob("example*.json")):
    m = MatchExtraction.model_validate_json(f.read_text(encoding="utf-8"))
    for goal in m.goals:
        team = m.home.name if goal.scoring_team == "home" else m.away.name
        expected[team] += 1

if result.get("error"):
    print("❌ Query error:", result["error"])
else:
    got = {row["team"]: row["goals"] for row in result["rows"]}
    print("expected  :", dict(expected))
    print("your query:", got)
    print("✅ Your query matches the Python aggregate!" if got == dict(expected)
          else "❌ Counts differ — check your aggregation (and that you grouped by team).")
"""
        ),
        # 5 · agent
        md(
            """
## 5 · The agent

The agent turns a natural-language question into Cypher using **tool-calling**: it asks for the
schema, validates a query, runs it, and paraphrases the answer — recovering from errors along
the way. Watch one run:
"""
        ),
        code(
            """
from src.agent.agent import ask

result = ask("What was the score between Cirera and L'Estartit?")
print("\\nAnswer:", result.answer)
print("Cypher attempts:")
for i, a in enumerate(result.cypher_attempts, 1):
    print(f"  [{i}] ok={a['ok']} rows={a['rows']}  {a['query'][:70].strip()}")
"""
        ),
        md(
            """
### 📝 Your turn (A) — ask your own question

Replace the question with one of your own about the 3 matches (scores, scorers, cards, stadiums,
referees…). Run it and read the Cypher the agent generated above the answer.
"""
        ),
        code(pick(question_skeleton, question_solution)),
        code(
            """
# ✅ check
assert result.answer and result.answer.strip(), "❌ The agent returned an empty answer."
print("✅ The agent answered. Scroll up to see the Cypher it wrote and ran.")
"""
        ),
        md(
            """
### 📝 Your turn (B) — change the agent's tone

The agent's behaviour comes from a **system prompt**. You can append one instruction to it at
runtime (no file editing) and see how the answer changes. Try a very formal tone, a playful one,
or "always answer in Catalan".
"""
        ),
        code(pick(tone_skeleton, tone_solution)),
        code(
            """
# ✅ check
assert result.answer and result.answer.strip(), "❌ Empty answer."
print("✅ Compare this answer's tone with the one from section 5. Same facts, different style.")
print("   (Re-run the cell above with a different TONE_INSTRUCTION to experiment.)")
"""
        ),
    ]
    return cells


# ════════════════════════════════════════════════════════════════════════════
# Part 2 — at scale (canonical notebook only)
# ════════════════════════════════════════════════════════════════════════════
def part2_cells() -> list[dict]:
    return [
        md(
            """
---
# Part 2 — At Scale (1793 reports)

You've built every component by hand. Now watch the *same* pipeline run over the full official
dataset of **1793** FCF match reports. Extraction was pre-computed on a GPU server (and already
downloaded in Setup), so here we focus on ingestion and querying at scale.

> The **2B agent model is already loaded** from Part 1 — Part 2 reuses it as-is.
"""
        ),
        code(
            """
# Reset the agent's system prompt in case you tweaked its tone in Part 1.
from src.agent import prompts
if hasattr(prompts, "_BASE_SYSTEM_PROMPT"):
    prompts.SYSTEM_PROMPT = prompts._BASE_SYSTEM_PROMPT
"""
        ),
        md(
            """
### Ingest all 1793 reports

The 3 reports from Part 1 are already in the graph; `ingest_full()` MERGEs the full dataset on
top (idempotent). Expect a few minutes on AuraDB Free.
"""
        ),
        code(
            """
from src.graph.ingest import ingest_full

# Reads data/extracted_full/<model-tag>/*.json and MERGEs everything into Neo4j.
counts = ingest_full()
"""
        ),
        code(
            """
from rich.table import Table
from rich.console import Console

table = Table(title="Node counts after ingestion")
table.add_column("Label", style="bold cyan")
table.add_column("Count", justify="right")
for label, count in sorted(counts.items()):
    table.add_row(label, str(count))
Console().print(table)

print(f"\\nMatches ingested: {counts.get('Match', 0)}")
assert counts.get("Match", 0) > 0 and counts.get("Goal", 0) > 0, \\
    "Graph looks empty — check the download and ingest steps."
print("✅ Graph populated.")
"""
        ),
        md(
            """
### Interactive graph visualization

The visualization is built with **pyvis** — a force-directed graph rendered as self-contained
HTML. Node colors reflect labels; hover over nodes and edges for details.

> You can also explore the graph interactively at [console.neo4j.io](https://console.neo4j.io).
"""
        ),
        code(
            """
from src.graph.visualize import render_graph

render_graph(limit=300)
"""
        ),
        md(
            """
### The agent at scale

The agent is unchanged — only the graph got bigger. A couple of demo questions over the full
dataset:
"""
        ),
        md(
            """
### Q1 · Aggregation

The agent needs to traverse `Match → Goal → Player` and aggregate with `COUNT`.
"""
        ),
        code(
            """
from rich.panel import Panel
from rich.console import Console

result = ask("Which player scored the most goals in matchday 29?")
Console().print(Panel(result.answer, title="Answer", style="bold green"))
"""
        ),
        md(
            """
### Q2 · Multi-hop traversal

The agent must first find which team conceded 6 goals, then find the stadium where that match
was played.
"""
        ),
        code(
            """
result = ask("In which stadium did the team that conceded 6 goals play?")
Console().print(Panel(result.answer, title="Answer", style="bold green"))
"""
        ),
        md(
            """
### Inspecting a full agent trace

Every conversation is persisted as JSON in `out/agent_traces/`. Let's inspect the latest one:
"""
        ),
        code(
            """
import json
from src.common.paths import TRACES_DIR
from rich.syntax import Syntax
from rich.console import Console

latest_trace = sorted(TRACES_DIR.glob("*.json"))[-1]
trace = json.loads(latest_trace.read_text())

print(f"Trace file : {latest_trace.name}")
print(f"Question   : {trace['question']}")
print(f"Iterations : {len([m for m in trace['messages'] if m.get('role') == 'tool'])}")
print(f"Answer     : {trace['answer']}")
print("\\nCypher attempts:")
for i, a in enumerate(trace['cypher_attempts'], 1):
    status = "✅" if a['ok'] else "❌"
    print(f"  [{i}] {status} rows={a['rows']}")
    Console().print(Syntax(a['query'], "cypher", theme="monokai", word_wrap=True))
"""
        ),
        md(
            """
---
## Conclusion & Key Takeaways

| Concept | How it's applied here |
|---|---|
| **Vision LLM as parser** | Qwen3.5-4B reads PDFs as images — no OCR, no layout heuristics |
| **Structured outputs** | Pydantic schema → JSON Schema → grammar-constrained decoding in llama.cpp |
| **Open models in Colab** | Two Qwen3.5 GGUFs via `llama-server`; swap to fit a small GPU |
| **Knowledge graph** | Neo4J with MERGE — idempotent, queryable, explainable |
| **Agentic RAG** | Tool-calling loop: schema → validate → run → recover → answer |
| **Read-only safety** | Regex guard prevents any write query from the agent |
| **Colab-compatible** | No Docker, no API keys — AuraDB Free + local GGUF models |

### What to explore next

- **Richer ontology**: add substitutions, match events, weather, attendance
- **Bigger agent model**: swap `Qwen3.5-2B` for `Qwen3.5-4B`/`9B` if your GPU allows
- **Vector + graph hybrid**: embed player names for fuzzy matching on top of exact Cypher
- **Multi-document reasoning**: questions that span several matches or seasons
- **Evaluation**: build a benchmark of Q&A pairs and measure answer accuracy automatically
"""
        ),
    ]


def build_canonical() -> dict:
    cells = header_cells() + setup_cells() + part1_cells(solved=False) + part2_cells()
    return {"cells": cells, "metadata": NB_METADATA, "nbformat": 4, "nbformat_minor": 5}


def build_solutions() -> dict:
    banner = md(
        """
> ✅ **Part 1 — Solutions.** This notebook is the interactive lab with every **📝 Your turn**
> exercise already filled in. Use it to check your work or to run Part 1 end-to-end without
> editing anything. (Part 2 has no exercises, so it's omitted here — see the main notebook.)
"""
    )
    cells = header_cells() + [banner] + setup_cells() + part1_cells(solved=True)
    return {"cells": cells, "metadata": NB_METADATA, "nbformat": 4, "nbformat_minor": 5}


def main() -> None:
    CANONICAL.write_text(json.dumps(build_canonical(), ensure_ascii=False, indent=1), encoding="utf-8")
    SOLUTIONS.write_text(json.dumps(build_solutions(), ensure_ascii=False, indent=1), encoding="utf-8")
    for nb_path in (CANONICAL, SOLUTIONS):
        nb = json.loads(nb_path.read_text(encoding="utf-8"))
        print(f"{nb_path.name}: {len(nb['cells'])} cells")


if __name__ == "__main__":
    main()
