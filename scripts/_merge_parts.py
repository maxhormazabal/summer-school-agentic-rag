"""Merge the Part 1 lab + Part 2 scale flow into ONE canonical notebook.

The user wants a single notebook: shared setup → Part 1 (interactive lab on the 3 example
reports, with fill-in exercises) → Part 2 (operational, the 1793 pre-computed dataset).

Sources:
  P1 = summer_school_part1_lab.ipynb              (setup + Part 1 lab)
  C  = summer_school_document_agentic_rag_tutorial.ipynb  (already swapped to the 1793 flow = Part 2)

Output overwrites C. The standalone P1 file is removed afterwards.
Run once: `./.venv/bin/python scripts/_merge_parts.py`.
"""
import json
from pathlib import Path

P1_PATH = Path("summer_school_part1_lab.ipynb")
C_PATH = Path("summer_school_document_agentic_rag_tutorial.ipynb")

p1 = json.loads(P1_PATH.read_text(encoding="utf-8"))
c = json.loads(C_PATH.read_text(encoding="utf-8"))
P1 = p1["cells"]
C = c["cells"]


def clean(cell):
    cell = json.loads(json.dumps(cell))  # deep copy
    if cell["cell_type"] == "code":
        cell["outputs"] = []
        cell["execution_count"] = None
    cell.setdefault("metadata", {})
    return cell


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


def assert_head(cell, needle, where):
    head = "".join(cell["source"])
    assert needle in head, f"{where}: expected to find {needle!r}, got: {head[:80]!r}"


# sanity: confirm a few key source cells are where we expect before pulling them
assert_head(C[1], "import base64", "C[1] mermaid")
assert_head(C[10], "Consolidated dataset download", "C[10] download")
assert_head(C[34], "ingest_full", "C[34] ingest_full")
assert_head(C[39], "render_graph", "C[39] render_graph")
assert_head(P1[4], 'backend for each role', "P1[4] model choice")
assert_head(P1[23], "apply_constraints", "P1[23] ingest 3")

cells = []

# ── Combined title ───────────────────────────────────────────────────────────────────
cells.append(md('''\
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

| Stage | What happens |
|---|---|
| **1 — Ontology** | Define the domain as Pydantic models |
| **2 — VLM Extraction** | A vision model reads PDF pages → structured JSON |
| **3 — Knowledge Graph** | JSON → Neo4J nodes & relationships (MERGE, idempotent) |
| **4 — Agentic RAG** | Natural language → Cypher → answer via tool-calling |
'''))

# ── Shared setup ──────────────────────────────────────────────────────────────────────
cells.append(clean(C[1]))     # mermaid diagram
cells.append(clean(C[2]))     # domain blurb
cells.append(md("## 0 · Setup\n\nCredentials, model choice, dependencies, connectivity — shared by both parts."))
cells.append(clean(C[4]))     # OpenAI key note
cells.append(clean(P1[2]))    # credentials
cells.append(clean(P1[3]))    # Choose your models (md)
cells.append(clean(P1[4]))    # model choice (code)
cells.append(clean(C[6]))     # env / clone / deps
cells.append(clean(C[7]))     # connectivity header
cells.append(clean(P1[7]))    # connectivity (backend-aware)

# ── PART 1 — interactive lab (3 reports) ─────────────────────────────────────────────
cells.append(md('''\
---
# Part 1 — Interactive Lab

Hands-on with **3 sample match reports** — small enough to *touch things* and see what happens.

> ⚠️ **How to use Part 1**
> - Edit **only** the cells marked **📝 Your turn**. Everything else is scaffolding.
> - Each 📝 exercise is followed by a **✅ / ❌ check** cell.
> - Broke something? **Re-run from the top.** Nothing here is destructive.

Part 1 uses the 3 reports shipped in the repo (`data/`), so **no download is needed** — that
comes in Part 2.
'''))
for i in range(8, 35):        # P1 lab body (domain → agent exercises), excludes its standalone wrap [35]
    cells.append(clean(P1[i]))

# ── PART 2 — at scale (1793 reports) ─────────────────────────────────────────────────
cells.append(md('''\
---
# Part 2 — At Scale (1793 reports)

You've built every component by hand. Now watch the *same* pipeline run over the full official
dataset of **1793** FCF match reports. Extraction was pre-computed on a GPU server, so here we
download the artifacts and focus on ingestion and querying at scale.

> The model backends you chose at the top still apply (the agent uses `AGENT_BACKEND`).
'''))
cells.append(clean(C[10]))    # download the 1793 PNG + JSON zips
cells.append(md('''\
### Ingest all 1793 reports

The 3 reports from Part 1 are already in the graph; `ingest_full()` now MERGEs the full dataset
on top (idempotent). Expect a few minutes on AuraDB Free.
'''))
cells.append(clean(C[34]))    # ingest_full()
cells.append(clean(C[35]))    # counts + soft asserts
cells.append(clean(C[38]))    # graph viz header
cells.append(clean(C[39]))    # render_graph
cells.append(md('''\
### The agent at scale

The agent is unchanged — only the graph got bigger. A couple of demo questions over the full
dataset (these will be expanded for the full-dataset narrative):
'''))
cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
              "source": (
                  "# Reset the agent's system prompt in case you tweaked its tone in Part 1.\n"
                  "from src.agent import prompts\n"
                  "if hasattr(prompts, \"_BASE_SYSTEM_PROMPT\"):\n"
                  "    prompts.SYSTEM_PROMPT = prompts._BASE_SYSTEM_PROMPT\n"
              ).splitlines(keepends=True)})
cells.append(clean(C[48]))    # Q2 md (aggregation)
cells.append(clean(C[49]))    # Q2 code
cells.append(clean(C[50]))    # Q3 md (multi-hop)
cells.append(clean(C[51]))    # Q3 code
cells.append(clean(C[58]))    # trace header
cells.append(clean(C[59]))    # trace inspection
cells.append(clean(C[60]))    # conclusion

# ── write ─────────────────────────────────────────────────────────────────────────────
c["cells"] = cells
C_PATH.write_text(json.dumps(c, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
n_code = sum(1 for x in cells if x["cell_type"] == "code")
print(f"Wrote {C_PATH} with {len(cells)} cells ({n_code} code, {len(cells)-n_code} markdown).")
