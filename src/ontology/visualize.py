from __future__ import annotations

import graphviz

from src.common.paths import OUT_DIR
from src.common.logging import console

# Node colors by category
_COLORS = {
    "Match": "#4A90D9",
    "Team": "#E67E22",
    "Player": "#27AE60",
    "Coach": "#8E44AD",
    "Stadium": "#C0392B",
    "Referee": "#16A085",
    "Goal": "#F39C12",
    "Card": "#E74C3C",
}

_RELATIONS = [
    ("Match", "HOME_TEAM", "Team"),
    ("Match", "AWAY_TEAM", "Team"),
    ("Match", "PLAYED_AT", "Stadium"),
    ("Match", "OFFICIATED_BY", "Referee"),
    ("Match", "HAS_GOAL", "Goal"),
    ("Match", "HAS_CARD", "Card"),
    ("Goal", "SCORED_BY", "Player"),
    ("Goal", "FOR_TEAM", "Team"),
    ("Card", "GIVEN_TO_PLAYER", "Player"),
    ("Card", "GIVEN_TO_COACH", "Coach"),
    ("Card", "AGAINST", "Team"),
    ("Player", "APPEARED_IN", "Match"),
    ("Player", "PLAYS_FOR", "Team"),
    ("Coach", "COACHED", "Team"),
]

_MERMAID_TEMPLATE = """\
graph LR
{edges}
"""


def render_ontology() -> graphviz.Source:
    """Render the ontology as a PNG and return a graphviz.Source for inline display."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dot = graphviz.Digraph("ontology", comment="FCF Match Ontology")
    dot.attr(rankdir="LR", fontsize="11", bgcolor="white")
    dot.attr("node", shape="box", style="filled,rounded", fontname="Helvetica", fontsize="10")
    dot.attr("edge", fontname="Helvetica", fontsize="9")

    for label, color in _COLORS.items():
        dot.node(label, label, fillcolor=color, fontcolor="white")

    for src, rel, dst in _RELATIONS:
        dot.edge(src, dst, label=rel)

    out_path = OUT_DIR / "ontology"
    dot.render(str(out_path), format="png", cleanup=True)
    console.print(f"[green]Ontology PNG → {out_path}.png[/green]")

    # Write Mermaid equivalent
    mmd_lines = [f"    {src} -->|{rel}| {dst}" for src, rel, dst in _RELATIONS]
    mmd_content = _MERMAID_TEMPLATE.format(edges="\n".join(mmd_lines))
    mmd_path = OUT_DIR / "ontology.mmd"
    mmd_path.write_text(mmd_content, encoding="utf-8")
    console.print(f"[green]Ontology Mermaid → {mmd_path}[/green]")

    return graphviz.Source(dot.source)
