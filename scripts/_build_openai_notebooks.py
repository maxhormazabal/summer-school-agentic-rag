"""One-off: revert the two course notebooks from the Qwen3.5/llama.cpp in-Colab setup
(PLAN.md §15) back to OpenAI GPT (gpt-4o extraction · gpt-4o-mini agent).

The `src/` code is already backend-agnostic (`src/common/llm.py` defaults to OpenAI), so
only the notebooks need changing: drop the llama.cpp build / GGUF download / model-server /
model-swap cells, restore OpenAI credentials + connectivity, and set the role→model env.

Strategy: operate on the *existing* notebooks (the source of truth for every non-model cell —
ontology, exercises, graph, agent, Part 2). Match cells by stable content markers, then
either REPLACE the source or DROP the cell. Idempotent: matching markers are unique to the
Qwen variant; once converted, re-running is a no-op (markers no longer present → warns).

Usage:  python scripts/_build_openai_notebooks.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "summer_school_document_agentic_rag_tutorial.ipynb"
SOLUTIONS = ROOT / "summer_school_part1_solutions.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def code(text: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": text.rstrip("\n").splitlines(keepends=True),
    }


# ── New / replacement cell contents (OpenAI) ──────────────────────────────────

CREDS_MD = md("""\
### Credentials

You need two things, both free:

1. A **Neo4J AuraDB** instance ([console.neo4j.io](https://console.neo4j.io)) — paste its URI,
   user and password below.
2. An **OpenAI API key** ([platform.openai.com](https://platform.openai.com/api-keys)) — the
   extraction (vision) and the agent both call OpenAI. In Colab, the cleanest way is to store it
   as a **Secret** (🔑 in the left sidebar) named `OPENAI_API_KEY`; otherwise paste it below or
   you'll be prompted.
""")

CREDS_CODE = code('''\
import os, getpass

# ── Neo4J AuraDB (free) — paste yours ─────────────────────────────────────────
NEO4J_URI      = '<paste-your-neo4j-uri>'        # e.g. neo4j+s://<id>.databases.neo4j.io
NEO4J_USERNAME = '<paste-your-neo4j-user>'       # default: neo4j
NEO4J_PASSWORD = '<paste-your-neo4j-password>'
NEO4J_DATABASE = '<paste-your-neo4j-database>'    # usually 'neo4j'; leave as-is to use the server default
# ──────────────────────────────────────────────────────────────────────────────

# Only export non-placeholder values, so a local .env (or Colab Secrets) is preserved.
for _k, _v in {
    "NEO4J_URI": NEO4J_URI, "NEO4J_USERNAME": NEO4J_USERNAME,
    "NEO4J_PASSWORD": NEO4J_PASSWORD, "NEO4J_DATABASE": NEO4J_DATABASE,
}.items():
    if _v and not _v.startswith("<"):
        os.environ[_k] = _v

# ── OpenAI API key ────────────────────────────────────────────────────────────
OPENAI_API_KEY = ''   # leave empty to use Colab Secrets, an existing env var, or a prompt
if OPENAI_API_KEY:
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
elif not os.environ.get("OPENAI_API_KEY"):
    try:
        from google.colab import userdata
        os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")
    except Exception:
        os.environ["OPENAI_API_KEY"] = getpass.getpass("OPENAI_API_KEY: ")

print("Credentials set ✓")
''')

MODELS_MD = md("""\
### Models — OpenAI GPT

This system is **backend-agnostic** (`src/common/llm.py`): each role independently targets a
backend by environment variable. Here both roles use OpenAI.

| Role | Model | Why |
|---|---|---|
| **Extraction** | `gpt-4o` | Reads the report *image* → JSON. Needs vision + strict structured output. |
| **Agent** | `gpt-4o-mini` | Turns questions into Cypher via tool-calls. Light, fast, cheap. |

> No GPU and no model downloads — the calls go to the OpenAI API. Extraction runs only on a few
> sample reports (Part 1); the 1793-report dataset (Part 2) is pre-computed, so total OpenAI
> usage stays tiny.
""")

MODELS_CODE = code('''\
# ── Role → OpenAI model ───────────────────────────────────────────────────────
import os

os.environ["EXTRACTION_BACKEND"] = "openai"
os.environ["EXTRACTION_MODEL"]   = "gpt-4o"        # vision: report image → JSON
os.environ["AGENT_BACKEND"]      = "openai"
os.environ["AGENT_MODEL"]        = "gpt-4o-mini"   # text: question → Cypher (tool-calls)

# Drop any leftover local-server overrides so nothing routes to a local endpoint.
for _k in ("LOCAL_VLLM_BASE_URL", "LOCAL_VLLM_MODEL", "LOCAL_VLLM_API_KEY"):
    os.environ.pop(_k, None)

print("Extraction → openai ·", os.environ["EXTRACTION_MODEL"])
print("Agent      → openai ·", os.environ["AGENT_MODEL"])
''')

BOOTSTRAP_CODE = code('''\
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
    # System deps for the pipeline: poppler (PDF→image) + graphviz (ontology diagram).
    subprocess.run(
        ["apt-get", "install", "-y", "-q", "poppler-utils", "graphviz"],
        capture_output=True, check=True,
    )
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "gdown", "openai"], check=True)
elif COLAB_SIMULATE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=True)

REPO_ROOT = os.path.abspath(".")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

mode = "Google Colab" if IN_COLAB else ("Colab Simulation" if COLAB_SIMULATE else "Local Dev")
print(f"Environment : {mode}")
print(f"Repo root   : {REPO_ROOT}")
''')

CONN_MD = md("""\
### Connectivity check

Confirm both services are reachable before going further: a one-token ping to OpenAI and a
`RETURN 1` against Neo4J.
""")

CONN_CODE = code('''\
from rich.table import Table
from rich.console import Console
from src.graph.neo4j_client import Neo4jClient
from src.common.llm import get_client_and_model

console = Console()
t = Table(title="Connectivity")
for col in ("Service", "Status", "Detail"):
    t.add_column(col)

ok = True

# OpenAI — a tiny chat call validates the key and the agent model.
try:
    _client, _model = get_client_and_model("agent")
    _client.chat.completions.create(
        model=_model, messages=[{"role": "user", "content": "ping"}], max_tokens=5,
    )
    t.add_row("OpenAI", "✅", _model)
except Exception as e:
    t.add_row("OpenAI", "❌", str(e)[:70]); ok = False

# Neo4J
try:
    with Neo4jClient() as c:
        c.run_read("RETURN 1 AS x")
    t.add_row("Neo4J", "✅", "OK")
except Exception as e:
    t.add_row("Neo4J", "❌", str(e)[:70]); ok = False

console.print(t)
assert ok, "Fix connectivity before continuing."
''')


# ── Marker-based transform ────────────────────────────────────────────────────
# Each rule: (marker substring, action). action is ("replace", new_cell) or ("drop", None).
# Markers are chosen to be unique to the Qwen variant of each cell.

COMMON_RULES = [
    ("You only need a free", ("replace", CREDS_MD)),
    ('os.environ["NEO4J_URI"]', ("replace", CREDS_CODE)),
    ("Models — two Qwen3.5 GGUFs", ("replace", MODELS_MD)),
    ("In-Colab model choice (Qwen3.5 GGUF", ("replace", MODELS_CODE)),
    ("# ── Environment detection", ("replace", BOOTSTRAP_CODE)),
    ("Build `llama.cpp`", ("drop", None)),
    ("Build llama.cpp with CUDA", ("drop", None)),
    ("The model server (load / unload", ("drop", None)),
    ("def start_llama_server", ("drop", None)),
    ("### Connectivity check", ("replace", CONN_MD)),
    ("def neo4j_check", ("replace", CONN_CODE)),
    ("Load the VISION model", ("drop", None)),
    ("Swap models: unload vision", ("drop", None)),
    ("Free the vision model's VRAM", ("drop", None)),
    ("Load the AGENT model", ("drop", None)),
]

# Solutions notebook has no Part 2, so its Part-2 dataset download is dead weight → drop it.
SOLUTIONS_EXTRA_RULES = [
    ("Download the Part 2 dataset", ("drop", None)),
    ("Consolidated dataset download", ("drop", None)),
]


def convert(path: Path, rules: list) -> None:
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = nb["cells"]
    new_cells = []
    matched = {marker: False for marker, _ in rules}

    for cell in cells:
        src = "".join(cell["source"])
        action = None
        for marker, act in rules:
            if marker in src:
                action = act
                matched[marker] = True
                break
        if action is None:
            new_cells.append(cell)
        elif action[0] == "replace":
            new_cells.append(action[1])
        # "drop" → skip

    nb["cells"] = new_cells
    path.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    unmatched = [m for m, hit in matched.items() if not hit]
    print(f"{path.name}: {len(cells)} → {len(new_cells)} cells")
    if unmatched:
        print(f"  ⚠ markers not found (already converted?): {unmatched}")


if __name__ == "__main__":
    if not CANONICAL.exists() or not SOLUTIONS.exists():
        sys.exit("notebooks not found at repo root")
    convert(CANONICAL, COMMON_RULES)
    convert(SOLUTIONS, COMMON_RULES + SOLUTIONS_EXTRA_RULES)
    print("done.")
