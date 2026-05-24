"""Build `summer_school_part1_lab.ipynb` — the interactive Part 1 lab (3 sample reports).

Controlled, hands-on: students complete fill-in-the-blank exercises (📝 Your turn) for each
phase (ontology, extraction-quality, graph query, agent), each followed by a ✅/❌ check cell.
Model-agnostic: extraction and agent backends are chosen at the top (openai | local).

Run once: `./.venv/bin/python scripts/_build_part1.py`.
"""
import json
from pathlib import Path

OUT = Path("summer_school_part1_lab.ipynb")

def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}

def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": text.splitlines(keepends=True)}

cells = []

# ── 0. Title + disclaimer ───────────────────────────────────────────────────────────
cells.append(md('''\
<div align="center">
  <img src="https://raw.githubusercontent.com/maxhormazabal/summer-school-agentic-rag/refs/heads/main/tutorial_imgs/logo_red.svg" alt="Summer School DAG Logo" width="200"/>
</div>

# Part 1 — Interactive Lab

Welcome to the **hands-on lab**. You'll build the pieces of an Agentic RAG system on a small,
controlled dataset of **3 FCF match reports** — small enough that you can *touch things* and
see what happens under the hood.

> ⚠️ **How to use this notebook**
> - Edit **only** the cells marked **📝 Your turn**. Everything else is scaffolding.
> - Each 📝 exercise is followed by a **✅ / ❌ check** cell that tells you whether your code works.
> - Broke something? Just **re-run from the top** (or re-clone the repo). Nothing here is destructive.

| Stage | You will... |
|---|---|
| **1 · Ontology** | complete a Pydantic model |
| **2 · Extraction** | write a data-quality check |
| **3 · Graph** | write a Cypher query |
| **4 · Agent** | ask the agent & tune its behaviour |

In **Part 2** you'll see this exact system run at scale over **1793** real match reports.
'''))

# ── Setup ───────────────────────────────────────────────────────────────────────────
cells.append(md("## 0 · Setup\n\nCredentials, model choice, dependencies, connectivity."))

cells.append(code('''\
import os

# ── Paste your credentials here ───────────────────────────────────────────────
OPENAI_API_KEY='<paste-your-openai-key>'
NEO4J_URI='<paste-your-neo4j-uri>'         # e.g. neo4j+s://<id>.databases.neo4j.io
NEO4J_USERNAME='<paste-your-neo4j-user>'   # default: neo4j
NEO4J_PASSWORD='<paste-your-neo4j-password>'
NEO4J_DATABASE='<paste-your-neo4j-database>'  # default: neo4j
# ─────────────────────────────────────────────────────────────────────────────

os.environ["OPENAI_API_KEY"]  = OPENAI_API_KEY
os.environ["NEO4J_URI"]       = NEO4J_URI
os.environ["NEO4J_USERNAME"]  = NEO4J_USERNAME
os.environ["NEO4J_PASSWORD"]  = NEO4J_PASSWORD
os.environ["NEO4J_DATABASE"]  = NEO4J_DATABASE

print("Credentials set ✓")
'''))

cells.append(md('''\
### Choose your models

This system is **backend-agnostic**: the *extraction* model (reads PDF pages) and the *agent*
model (answers questions) are chosen independently. Each can be:

- **`"openai"`** — GPT-4o via the OpenAI API (needs `OPENAI_API_KEY`). Reliable; recommended.
- **`"local"`** — any OpenAI-compatible server (e.g. a vLLM serving Pixtral). Free, no key.

> ℹ️ A `"local"` server must support what the role needs: the **agent** needs structured
> tool-calls (start vLLM with `--enable-auto-tool-choice --tool-call-parser mistral`), and the
> **extraction** role needs robust vision + JSON-schema output. If unsure, keep `"openai"`.
'''))

cells.append(code('''\
# Pick a backend for each role: "openai" or "local"
EXTRACTION_BACKEND = "openai"   # reads the match-report image → JSON
AGENT_BACKEND      = "openai"   # answers questions via Cypher tool-calls

# Local OpenAI-compatible server (only used if a backend above is "local")
LOCAL_VLLM_BASE_URL = "http://158.109.8.116:8000/v1"
LOCAL_VLLM_MODEL    = "mistralai/Pixtral-12B-2409"

os.environ["EXTRACTION_BACKEND"] = EXTRACTION_BACKEND
os.environ["AGENT_BACKEND"]      = AGENT_BACKEND
os.environ["LOCAL_VLLM_BASE_URL"] = LOCAL_VLLM_BASE_URL
os.environ["LOCAL_VLLM_MODEL"]    = LOCAL_VLLM_MODEL

print(f"Extraction → {EXTRACTION_BACKEND}   |   Agent → {AGENT_BACKEND}")
if AGENT_BACKEND == "local":
    print("⚠️  Agent on a local server needs tool-call parsing enabled "
          "(vLLM: --enable-auto-tool-choice --tool-call-parser mistral).")
'''))

# env detection + clone + deps (reused from Part 2)
cells.append(code('''\
import sys, os, subprocess

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
    subprocess.run(["apt-get", "install", "-y", "-q", "poppler-utils", "graphviz"],
                   capture_output=True, check=True)
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                   check=True)
elif COLAB_SIMULATE:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                   check=True)

REPO_ROOT = os.path.abspath(".")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

mode = "Google Colab" if IN_COLAB else ("Colab Simulation" if COLAB_SIMULATE else "Local Dev")
print(f"Environment : {mode}")
print(f"Repo root   : {REPO_ROOT}")
'''))

cells.append(md("### Connectivity check\n\nVerify Neo4J and the model backends you chose are reachable."))

cells.append(code('''\
from rich.table import Table
from rich.console import Console
from src.graph.neo4j_client import Neo4jClient
from src.common.llm import get_client_and_model, backend_for

def connectivity_check() -> bool:
    rows = []
    try:
        with Neo4jClient() as c:
            c.run_read("RETURN 1 AS x")
        rows.append(("Neo4J", "✅", "OK"))
    except Exception as e:
        rows.append(("Neo4J", "❌", str(e)[:70]))

    for role in ("extraction", "agent"):
        b = backend_for(role)
        try:
            client, model = get_client_and_model(role)
            client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "ping"}], max_tokens=5)
            rows.append((f"{role} ({b})", "✅", model))
        except Exception as e:
            rows.append((f"{role} ({b})", "❌", str(e)[:70]))

    t = Table(title="Connectivity")
    for col in ("Service", "Status", "Detail"):
        t.add_column(col)
    for r in rows:
        t.add_row(*r)
    Console().print(t)
    return all(s == "✅" for _, s, _ in rows)

assert connectivity_check(), "Fix the issues above before continuing."
'''))

# ── 1. Domain ───────────────────────────────────────────────────────────────────────
cells.append(md('''\
## 1 · The domain — FCF match reports

Each report is a single PDF page (in Catalan) containing the lineups (**TITULARS** / **SUPLENTS**),
technical staff, goals (**GOLS**), cards (**TARGETES**), stadium and referee. The VLM reads the
**image** — no OCR. Let's look at one.
'''))

cells.append(code('''\
from pdf2image import convert_from_path
from IPython.display import display
from src.common.paths import DOCS_DIR

page = convert_from_path(str(DOCS_DIR / "example1.pdf"), dpi=110, first_page=1, last_page=1)[0]
display(page.resize((int(page.width * 0.6), int(page.height * 0.6))))
'''))

# ── 2. Ontology ─────────────────────────────────────────────────────────────────────
cells.append(md('''\
## 2 · Ontology

The ontology is just a set of **Pydantic models** describing what a match report contains.
`MatchExtraction` is the root; it nests `Team`, `Player`, `Goal`, `Card`, `Stadium`, `Referee`.
Here is the diagram:
'''))

cells.append(code('''\
from src.ontology.visualize import render_ontology
render_ontology()   # writes out/ontology.png and returns a displayable diagram
'''))

cells.append(md('''\
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
'''))

cells.append(code('''\
from pydantic import BaseModel
from typing import Literal
from src.ontology.schema import GoalType   # provided enum: regular | own | penalty

class MyGoal(BaseModel):
    # 📝 TODO: declare the six fields described in the table above.
    # Example syntax:  minute: int
    ...
'''))

cells.append(code('''\
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
'''))

# ── 3. Extraction ───────────────────────────────────────────────────────────────────
cells.append(md('''\
## 3 · Extraction (VLM → JSON)

The VLM receives the page image plus a domain prompt and returns JSON validated against the
ontology. The **3 sample reports are already extracted** into `data/extracted/`, so you don't
need to spend tokens. Here's the system prompt that guides it:
'''))

cells.append(code('''\
from src.extraction.vlm_extractor import _SYSTEM_PROMPT
print(_SYSTEM_PROMPT[:1100], "\\n...")
'''))

cells.append(md('''\
*(Optional)* Run the VLM **live** on one page using your `EXTRACTION_BACKEND`. With `"openai"`
this is fast and cheap; with a `"local"` server it may be slow or unsupported for vision — the
cached JSONs below work regardless.
'''))

cells.append(code('''\
RUN_LIVE_EXTRACTION = False   # set True to call the VLM live on example1

if RUN_LIVE_EXTRACTION:
    from pathlib import Path
    from src.extraction.vlm_extractor import extract
    m = extract(Path("data/images/example1.png"))
    print(f"{m.home.name} {m.score_home}-{m.score_away} {m.away.name} · goals={len(m.goals)}")
else:
    print("Skipping live extraction — using the 3 cached JSONs in data/extracted/.")
'''))

cells.append(md('''\
### 📝 Your turn — write a data-quality check

When you extract data automatically, you need cheap checks that it isn't hallucinated. Implement
`quality_check(m)` returning a dict with two booleans:

- **`goals_ok`** — the number of goals equals the final score: `len(m.goals) == m.score_home + m.score_away`
- **`scorers_ok`** — every goal's scorer appears in *some* lineup, after name normalisation.

Helpers: `normalize_name(text)`; lineups are `m.home.lineup` / `m.away.lineup`; each entry has
`entry.player.name`.
'''))

cells.append(code('''\
from src.common.ids import normalize_name
from src.ontology.schema import MatchExtraction

def quality_check(m: MatchExtraction) -> dict:
    # 📝 TODO: return {"goals_ok": <bool>, "scorers_ok": <bool>}
    # Hint: build a set of normalised player names from both lineups, then test each scorer.
    ...
'''))

cells.append(code('''\
# ✅ check — runs your function over the 3 cached reports
from pathlib import Path
from src.common.paths import EXTRACTED_DIR

all_ok = True
for f in sorted(EXTRACTED_DIR.glob("example*.json")):
    m = MatchExtraction.model_validate_json(f.read_text(encoding="utf-8"))
    r = quality_check(m) or {}
    print(f"  {f.name}: goals_ok={r.get('goals_ok')}  scorers_ok={r.get('scorers_ok')}")
    all_ok = all_ok and bool(r.get("goals_ok")) and bool(r.get("scorers_ok"))
print("✅ quality_check passes on all 3 reports." if all_ok
      else "❌ Not all checks pass — review your quality_check.")
'''))

# ── 4. Graph ────────────────────────────────────────────────────────────────────────
cells.append(md('''\
## 4 · The knowledge graph

We turn the JSON into Neo4J nodes and relationships. Ingestion uses `MERGE`, so it is
**idempotent** — running it twice doesn't duplicate anything. Let's load the 3 reports.
'''))

cells.append(code('''\
from src.graph.constraints import apply as apply_constraints
from src.graph.ingest import ingest_all

apply_constraints()
counts = ingest_all()   # ingests the 3 cached reports
print("Node counts:", counts)
'''))

cells.append(md('''\
### 📝 Your turn — count goals per team in Cypher

The graph has `(Goal)-[:FOR_TEAM]->(Team)` and every `Team` has a `name` property. **Complete
the query** so it returns one row per team with its goal count. Replace `___` with the right
aggregation.
'''))

cells.append(code('''\
from src.agent.tools import run_cypher

cypher = """
MATCH (g:Goal)-[:FOR_TEAM]->(t:Team)
RETURN t.name AS team, ___ AS goals
ORDER BY goals DESC
"""

result = run_cypher(cypher)
print(result)
'''))

cells.append(code('''\
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
    print("expected :", dict(expected))
    print("your query:", got)
    print("✅ Your query matches the Python aggregate!" if got == dict(expected)
          else "❌ Counts differ — check your aggregation (and that you grouped by team).")
'''))

# ── 5. Agent ────────────────────────────────────────────────────────────────────────
cells.append(md('''\
## 5 · The agent

The agent turns a natural-language question into Cypher using **tool-calling**: it asks for the
schema, validates a query, runs it, and paraphrases the answer — recovering from errors along
the way. Watch one run:
'''))

cells.append(code('''\
from src.agent.agent import ask

result = ask("What was the score between Cirera and L'Estartit?")
print("\\nAnswer:", result.answer)
print("Cypher attempts:")
for i, a in enumerate(result.cypher_attempts, 1):
    print(f"  [{i}] ok={a['ok']} rows={a['rows']}  {a['query'][:70].strip()}")
'''))

cells.append(md('''\
### 📝 Your turn (A) — ask your own question

Replace the question with one of your own about the 3 matches (scores, scorers, cards, stadiums,
referees…). Run it and read the Cypher the agent generated above the answer.
'''))

cells.append(code('''\
MY_QUESTION = "Which team scored the most goals?"   # 📝 TODO: change this

result = ask(MY_QUESTION)
print("\\nAnswer:", result.answer)
'''))

cells.append(code('''\
# ✅ check
assert result.answer and result.answer.strip(), "❌ The agent returned an empty answer."
print("✅ The agent answered. Scroll up to see the Cypher it wrote and ran.")
'''))

cells.append(md('''\
### 📝 Your turn (B) — change the agent's tone

The agent's behaviour comes from a **system prompt**. You can append one instruction to it at
runtime (no file editing) and see how the answer changes. Try a very formal tone, a playful one,
or "always answer in Catalan".
'''))

cells.append(code('''\
from src.agent import prompts

TONE_INSTRUCTION = "Answer in a very formal, ceremonious tone."   # 📝 TODO: change this

# Capture the base prompt once so re-running this cell with a new tone doesn't stack rules.
if not hasattr(prompts, "_BASE_SYSTEM_PROMPT"):
    prompts._BASE_SYSTEM_PROMPT = prompts.SYSTEM_PROMPT
prompts.SYSTEM_PROMPT = prompts._BASE_SYSTEM_PROMPT + "\\n\\nADDITIONAL STYLE RULE: " + TONE_INSTRUCTION

result = ask("What was the score between Cirera and L'Estartit?")
print("\\nAnswer:", result.answer)
'''))

cells.append(code('''\
# ✅ check
assert result.answer and result.answer.strip(), "❌ Empty answer."
print("✅ Compare this answer's tone with the one from section 5. Same facts, different style.")
print("   (Re-run the cell above with a different TONE_INSTRUCTION to experiment.)")
'''))

# ── 6. Wrap-up ──────────────────────────────────────────────────────────────────────
cells.append(md('''\
## 6 · Wrap-up

You just built every layer of an Agentic RAG system on 3 reports:

1. **Ontology** — completed a Pydantic model.
2. **Extraction** — wrote a quality check over VLM output.
3. **Graph** — queried Neo4J with your own Cypher.
4. **Agent** — asked questions in natural language and shaped the agent's behaviour.

➡️ **Part 2** runs this *same* pipeline over the full official dataset of **1793** match reports,
with the extraction already pre-computed. Now that you understand the components, you'll see how
it scales.
'''))

# ── assemble ────────────────────────────────────────────────────────────────────────
nb = {
    "cells": cells,
    "metadata": {
        "colab": {"provenance": []},
        "kernelspec": {"display_name": ".venv", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11.3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
print(f"Wrote {OUT} with {len(cells)} cells "
      f"({sum(1 for c in cells if c['cell_type']=='code')} code, "
      f"{sum(1 for c in cells if c['cell_type']=='markdown')} markdown).")
