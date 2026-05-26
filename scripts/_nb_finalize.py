"""One-off: two finishing touches on the canonical notebook (PLAN.md §16):

1. Move the Part-2 dataset download to the FRONT of Setup — right after the environment
   bootstrap (which is its hard prerequisite: it clones the repo and installs gdown), and
   BEFORE credentials/models/connectivity, so the slow download starts first.
2. Insert a markdown cell in "## 5 · The agent" explaining the robust name-search machinery
   (find_entity + parameterized Cypher + schema grounding).

Idempotent-ish: re-running is a no-op once the download markdown text marks it as moved.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NB = ROOT / "summer_school_document_agentic_rag_tutorial.ipynb"


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)}


SETUP_HEADING = md("""\
## 0 · Setup

Run this section top-to-bottom. We set up the environment and **download the dataset first**
(it's the slow part), then paste credentials and check connectivity.
""")

DOWNLOAD_MD = md("""\
### Download the dataset — first thing

This is the slow step, so we run it up front. We pull the **1793 pre-computed match reports**
(page images + extracted JSON) from Google Drive. It's idempotent — already-present files are
skipped. Part 1 only uses the 3 sample reports already in the repo, so you can keep reading
while this finishes; Part 2 needs it.
""")

SEARCH_MD = md("""\
> ### 🔎 How the agent finds entities (robust name search)
>
> Names in questions rarely match the graph literally: **L'Estartit** is stored as
> `L'ESTARTIT, U.E. A`, **Cirera** drops its club suffix, **Nayara Alfaro** is stored
> surname-first. Three pieces make the lookup robust — with no special-casing of any one name:
>
> 1. **`find_entity` tool** resolves a free-text name to its canonical graph `id`. It combines a
>    Neo4J **full-text (Lucene) index** over entity names with **token-coverage** scoring and a
>    **fuzzy** distance (`apoc.text.levenshteinSimilarity`), so it tolerates accents, apostrophes,
>    missing club suffixes, word order and typos. It covers every named entity — teams, players,
>    coaches, stadiums and referees.
> 2. **Parameterised Cypher**: the agent passes every value (the resolved id, numbers, …) as a
>    `$param` instead of pasting it into the query text. Apostrophes, accents and quotes can no
>    longer break the query, and it is injection-safe.
> 3. **Schema grounding**: the real graph schema (labels, relationships, properties) is injected
>    into the agent's system prompt, so it never invents relationships that don't exist.
>
> So the loop is: *question → `find_entity` (name → canonical id) → `validate_cypher` →
> `run_cypher` (with params) → answer.*
""")


def find(cells, *, kind, marker):
    for i, c in enumerate(cells):
        if c["cell_type"] == kind and marker in "".join(c["source"]):
            return i
    raise SystemExit(f"marker not found: {kind} :: {marker!r}")


def main():
    nb = json.loads(NB.read_text(encoding="utf-8"))
    cells = nb["cells"]

    if any("first thing" in "".join(c["source"]) for c in cells if c["cell_type"] == "markdown"):
        print("already finalized (download marked as moved) — no-op")
        return

    # Locate setup cells by content marker.
    i_domain = find(cells, kind="markdown", marker="**Domain:**")
    i_boot = find(cells, kind="code", marker="# ── Environment detection")
    i_dl_md = find(cells, kind="markdown", marker="Download the Part 2 dataset")
    i_dl_code = find(cells, kind="code", marker="Consolidated dataset download")
    i_cred_md = find(cells, kind="markdown", marker="### Credentials")
    i_cred_code = find(cells, kind="code", marker='os.environ["OPENAI_API_KEY"]')
    i_models_md = find(cells, kind="markdown", marker="### Models — OpenAI GPT")
    i_models_code = find(cells, kind="code", marker="Role → OpenAI model")
    i_conn_md = find(cells, kind="markdown", marker="### Connectivity check")
    i_conn_code = find(cells, kind="code", marker='Table(title="Connectivity")')

    boot, dl_code = cells[i_boot], cells[i_dl_code]
    cred_md, cred_code = cells[i_cred_md], cells[i_cred_code]
    models_md, models_code = cells[i_models_md], cells[i_models_code]
    conn_md, conn_code = cells[i_conn_md], cells[i_conn_code]

    setup_region = {i_boot, i_dl_md, i_dl_code, i_cred_md, i_cred_code,
                    i_models_md, i_models_code, i_conn_md, i_conn_code}
    # also drop the bare separator markdown sitting between domain and credentials
    for j in range(i_domain + 1, i_cred_md):
        if cells[j]["cell_type"] == "markdown" and "".join(cells[j]["source"]).strip() == "---":
            setup_region.add(j)

    head = [c for k, c in enumerate(cells) if k <= i_domain]
    tail = [c for k, c in enumerate(cells) if k > i_conn_code and k not in setup_region]

    new_setup = [
        SETUP_HEADING,
        boot,            # environment bootstrap (clones repo, installs gdown) — prerequisite
        DOWNLOAD_MD, dl_code,   # download FIRST
        cred_md, cred_code,
        models_md, models_code,
        conn_md, conn_code,
    ]
    cells = head + new_setup + tail

    # Insert the search-explanation markdown right after "## 5 · The agent".
    i_agent = find(cells, kind="markdown", marker="## 5 · The agent")
    cells.insert(i_agent + 1, SEARCH_MD)

    nb["cells"] = cells
    NB.write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"finalized: {len(cells)} cells; download moved to front of Setup; search md inserted.")


if __name__ == "__main__":
    main()
