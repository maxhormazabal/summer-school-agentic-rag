"""
tutorial.py — Entry point for the Agentic RAG on Football Graph tutorial.

Subcommands:
  check           Health-check OpenAI + Neo4J connections.
  stage1          Render ontology diagram.
  stage2          Extract match data from PDFs via VLM.
  stage3          Ingest data into Neo4J and visualize graph.
  stage4 ask "q"  Ask a single question to the agent.
  repl            Interactive question loop.
  demo            Run the 6 demo questions.
  all             Run stages 0-3 then demo.
"""

import argparse
import sys


def cmd_check(_args: argparse.Namespace) -> None:
    from src import setup
    ok = setup.check()
    sys.exit(0 if ok else 1)


def cmd_stage1(_args: argparse.Namespace) -> None:
    from src.ontology.visualize import render_ontology
    from src.common.logging import console
    src = render_ontology()
    console.print(f"[green]Ontology rendered.[/green]")
    console.print(src.source[:400] + "...")


def cmd_stage2(args: argparse.Namespace) -> None:
    from src.extraction.runner import run, inspect as vlm_inspect
    from src.common.logging import console
    run(force=getattr(args, "force", False))
    if hasattr(args, "inspect") and args.inspect is not None:
        img, data = vlm_inspect(args.inspect)
        import json
        from rich.panel import Panel
        from rich.syntax import Syntax
        console.print(Panel(Syntax(json.dumps(data, indent=2, ensure_ascii=False), "json"), title=f"example{args.inspect}.json"))


def cmd_stage3(_args: argparse.Namespace) -> None:
    from src.graph.constraints import apply as apply_constraints
    from src.graph.ingest import ingest_all
    from src.graph.visualize import render_graph
    from src.common.logging import console
    from rich.table import Table

    apply_constraints()
    counts = ingest_all()

    table = Table(title="Node counts after ingestion")
    table.add_column("Label", style="bold")
    table.add_column("Count")
    for label, count in sorted(counts.items()):
        table.add_row(label, str(count))
    console.print(table)

    iframe = render_graph()
    from src.common.paths import OUT_DIR
    console.print(f"[green]Graph saved to {OUT_DIR / 'graph.html'}[/green]")
    console.print("[dim]Tip: open out/graph.html in a browser, or use console.neo4j.io for interactive exploration.[/dim]")
    return iframe


def cmd_stage4(args: argparse.Namespace) -> None:
    from src.agent.agent import ask
    result = ask(args.question)
    from src.common.logging import console
    from rich.panel import Panel
    console.print(Panel(result.answer, title="Agent answer", style="bold green"))


def cmd_repl(_args: argparse.Namespace) -> None:
    from src.agent.agent import ask
    from src.common.logging import console
    from rich.panel import Panel
    console.print("[bold]REPL mode — type 'exit' or Ctrl-C to quit.[/bold]")
    while True:
        try:
            question = input("\nQuestion: ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if question.lower() in {"exit", "quit", "q"}:
            break
        if not question:
            continue
        result = ask(question)
        console.print(Panel(result.answer, title="Answer", style="bold green"))


DEMO_QUESTIONS = [
    "What was the score between Cirera and L'Estartit?",
    "Which player scored the most goals in matchday 29?",
    "In which stadium did the team that conceded 6 goals play?",
    "List the goals scored before minute 30.",
    "How many penalties were missed?",
    "Did any coach or team official receive a card?",
]


def cmd_demo(_args: argparse.Namespace) -> None:
    from src.agent.agent import ask
    from src.common.logging import console
    from rich.rule import Rule
    from rich.panel import Panel

    for i, question in enumerate(DEMO_QUESTIONS, 1):
        console.print(Rule(f"[bold cyan]Demo {i}/6[/bold cyan]"))
        console.print(f"[bold]Q:[/bold] {question}")
        result = ask(question)
        console.print(Panel(result.answer, title="Answer", style="bold green"))


def cmd_all(_args: argparse.Namespace) -> None:
    cmd_stage1(_args)
    cmd_stage2(_args)
    cmd_stage3(_args)
    cmd_demo(_args)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agentic RAG — Football Graph Tutorial")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Health-check connections")

    sub.add_parser("stage1", help="Render ontology diagram")

    p2 = sub.add_parser("stage2", help="Extract match data from PDFs via VLM")
    p2.add_argument("--force", action="store_true", help="Re-extract even if JSON exists")
    p2.add_argument("--inspect", type=int, metavar="N", help="Display image+JSON for example N")

    sub.add_parser("stage3", help="Ingest into Neo4J and visualize")

    p4 = sub.add_parser("stage4", help="Agent subcommands")
    p4_sub = p4.add_subparsers(dest="stage4_cmd", required=True)
    p4_ask = p4_sub.add_parser("ask", help="Ask a single question")
    p4_ask.add_argument("question", help="Question in natural language")

    sub.add_parser("repl", help="Interactive question loop")
    sub.add_parser("demo", help="Run all 6 demo questions")
    sub.add_parser("all", help="Run stages 1-3 then demo")

    args = parser.parse_args()

    dispatch = {
        "check": cmd_check,
        "stage1": cmd_stage1,
        "stage2": cmd_stage2,
        "stage3": cmd_stage3,
        "stage4": cmd_stage4,
        "repl": cmd_repl,
        "demo": cmd_demo,
        "all": cmd_all,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
