from __future__ import annotations

from src.common.logging import console
from src.common.paths import OUT_DIR
from src.graph.neo4j_client import Neo4jClient

_LABEL_COLORS = {
    "Match": "#4A90D9",
    "Team": "#E67E22",
    "Player": "#27AE60",
    "Coach": "#8E44AD",
    "Stadium": "#C0392B",
    "Referee": "#16A085",
    "Goal": "#F39C12",
    "Card": "#E74C3C",
}


def render_graph(limit: int = 300):
    """Render the Neo4J graph as a self-contained HTML file using pyvis."""
    from pyvis.network import Network
    from IPython.display import HTML

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "graph.html"

    net = Network(
        cdn_resources="in_line",
        height="600px",
        width="100%",
        directed=True,
    )

    with Neo4jClient() as client:
        rows = client.run_read(
            """
            MATCH (n)-[r]->(m)
            RETURN
                elementId(n) AS n_eid, labels(n) AS n_labels, properties(n) AS n_props,
                type(r) AS r_type,
                elementId(m) AS m_eid, labels(m) AS m_labels, properties(m) AS m_props
            LIMIT $limit
            """,
            limit=limit,
        )

    added: set[str] = set()

    def _add_node(eid: str, labels: list, props: dict) -> None:
        if eid in added:
            return
        added.add(eid)
        first_label = labels[0] if labels else ""
        color = _LABEL_COLORS.get(first_label, "#999999")
        display = str(props.get("name", props.get("id", eid)))[:30]
        title = f"{first_label}: {display}"
        net.add_node(eid, label=display, color=color, title=title)

    for row in rows:
        _add_node(row["n_eid"], row["n_labels"], row["n_props"])
        _add_node(row["m_eid"], row["m_labels"], row["m_props"])
        net.add_edge(row["n_eid"], row["m_eid"], title=row["r_type"], label=row["r_type"])

    net.save_graph(str(out_path))
    console.print(f"[green]Graph saved → {out_path}[/green]")
    return HTML(out_path.read_text(encoding="utf-8"))
