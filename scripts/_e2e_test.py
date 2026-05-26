"""TEMPORARY end-to-end test of the OpenAI (GPT) pipeline — mirrors the notebook flow.

Sets the same role→model env the notebooks set, then exercises every phase against a real
OpenAI key and a local Neo4j. Part 2 ingest is capped to a subset (PART2_LIMIT) to avoid
dumping 1793 reports into a throwaway DB. Run with the test env exported (see _e2e_run.sh).

  PART1_EXTRACT=1  → also do a live gpt-4o extraction on one sample (costs ~1 call)
  PART2_LIMIT=N    → ingest only N of the 1793 reports in Part 2 (default 25; 0 = all)
"""
from __future__ import annotations

import os
from pathlib import Path

# ── Models, exactly as the notebooks set them ─────────────────────────────────
os.environ["EXTRACTION_BACKEND"] = "openai"
os.environ["EXTRACTION_MODEL"]   = "gpt-4o"
os.environ["AGENT_BACKEND"]      = "openai"
os.environ["AGENT_MODEL"]        = "gpt-4o-mini"
for _k in ("LOCAL_VLLM_BASE_URL", "LOCAL_VLLM_MODEL", "LOCAL_VLLM_API_KEY"):
    os.environ.pop(_k, None)

import sys
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.llm import get_client_and_model, backend_for  # noqa: E402


def banner(s): print("\n" + "=" * 78 + f"\n{s}\n" + "=" * 78)


def test_connectivity():
    banner("CONNECTIVITY (OpenAI + Neo4j)")
    c, m = get_client_and_model("agent")
    c.chat.completions.create(model=m, messages=[{"role": "user", "content": "ping"}], max_tokens=5)
    print(f"  OpenAI ✓  (agent={m}, extraction={get_client_and_model('extraction')[1]}, "
          f"backends: extraction={backend_for('extraction')}, agent={backend_for('agent')})")
    from src.graph.neo4j_client import Neo4jClient
    with Neo4jClient() as cli:
        cli.run_read("RETURN 1 AS x")
    print("  Neo4j ✓")


def test_ontology():
    banner("ONTOLOGY (render_ontology → out/ontology.png)")
    from src.ontology.visualize import render_ontology
    render_ontology()
    p = ROOT / "out" / "ontology.png"
    print(f"  ontology.png exists: {p.exists()} ({p.stat().st_size} bytes)")


def test_extraction_live():
    if os.environ.get("PART1_EXTRACT") != "1":
        print("\n(skip live gpt-4o extraction; set PART1_EXTRACT=1 to enable)")
        return
    banner("EXTRACTION LIVE (gpt-4o vision on example1.png)")
    from src.extraction.pdf_to_images import convert_all
    from src.extraction.vlm_extractor import extract
    from src.common.paths import IMAGES_DIR
    convert_all()
    png = sorted(IMAGES_DIR.glob("example*.png"))[0]
    m = extract(png)
    print(f"  {png.name}: {m.home.name} {m.score_home}-{m.score_away} {m.away.name} | "
          f"goals={len(m.goals)} subs_home={sum(1 for e in m.home.lineup if e.role=='sub')}")


def test_graph_part1():
    banner("GRAPH — Part 1 (constraints + ingest_all over 3 examples)")
    from src.graph.constraints import apply as apply_constraints
    from src.graph.ingest import ingest_all
    apply_constraints()
    counts = ingest_all()
    print("  node counts:", counts)
    return counts


def test_cypher_tool():
    banner("CYPHER TOOL (run_cypher read-only)")
    from src.agent.tools import run_cypher
    r = run_cypher("MATCH (m:Match) RETURN count(m) AS matches")
    print("  matches:", r.get("rows"))
    blocked = run_cypher("CREATE (x:Foo) RETURN x")
    print("  write blocked:", blocked.get("error"))


def test_agent_part1():
    banner("AGENT — Part 1 (gpt-4o-mini tool-calling)")
    from src.agent.agent import ask
    res = ask("What was the score between Cirera and L'Estartit?")
    print("  answer:", res.answer)
    print("  cypher attempts:", [(a["ok"], a["rows"]) for a in res.cypher_attempts])


def test_part2():
    banner("PART 2 — ingest_full subset + agent at scale")
    from src.common.paths import EXTRACTED_FULL_DIR
    from src.graph.ingest import ingest_full
    limit = int(os.environ.get("PART2_LIMIT", "25"))
    jsons = sorted(EXTRACTED_FULL_DIR.rglob("*.json"))
    # filter out bookkeeping files
    jsons = [p for p in jsons if not p.name.startswith("_")]
    print(f"  found {len(jsons)} extracted JSONs under {EXTRACTED_FULL_DIR}")
    if not jsons:
        print("  ⚠ no Part-2 JSONs present — download extracted_full.zip first. Skipping.")
        return
    if limit and len(jsons) > limit:
        # Stage a temp subdir with `limit` files so ingest_full only sees those.
        import tempfile, shutil
        tmp = Path(tempfile.mkdtemp(prefix="ss_part2_"))
        for p in jsons[:limit]:
            shutil.copy(p, tmp / p.name)
        counts = ingest_full(directory=tmp)
        shutil.rmtree(tmp)
        print(f"  ingest_full(subset={limit}) counts:", counts)
    else:
        counts = ingest_full()
        print(f"  ingest_full(all={len(jsons)}) counts:", counts)
    from src.agent.agent import ask
    res = ask("Which team scored the most goals?")
    print("  agent answer:", res.answer)


if __name__ == "__main__":
    test_connectivity()
    test_ontology()
    test_extraction_live()
    test_graph_part1()
    test_cypher_tool()
    test_agent_part1()
    test_part2()
    banner("E2E TEST COMPLETE")
