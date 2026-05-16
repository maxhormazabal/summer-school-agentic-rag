from src.common.config import get_secret
from src.common.logging import console


def check() -> bool:
    """Ping OpenAI and Neo4J, print a Rich table, return True if both OK."""
    from rich.table import Table

    results = {}

    # --- OpenAI ping ---
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
        client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=5,
        )
        results["OpenAI"] = ("✅", "OK")
    except Exception as exc:
        results["OpenAI"] = ("❌", str(exc)[:80])

    # --- Neo4J ping ---
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            get_secret("NEO4J_URI"),
            auth=(get_secret("NEO4J_USER"), get_secret("NEO4J_PASSWORD")),
            connection_timeout=15,
        )
        with driver.session() as session:
            session.run("RETURN 1").single()
        driver.close()
        results["Neo4J"] = ("✅", "OK")
    except Exception as exc:
        results["Neo4J"] = ("❌", str(exc)[:80])

    table = Table(title="Environment check")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Detail")
    for service, (status, detail) in results.items():
        table.add_row(service, status, detail)
    console.print(table)

    return all(status == "✅" for status, _ in results.values())
