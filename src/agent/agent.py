from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from src.agent.prompts import build_messages
from src.agent.tools import TOOL_SPECS, get_graph_schema, validate_cypher, run_cypher
from src.common.config import get_secret
from src.common.logging import console
from src.common.paths import TRACES_DIR


@dataclass
class AgentResult:
    answer: str
    cypher_attempts: list[dict] = field(default_factory=list)
    trace_path: Path = field(default_factory=lambda: Path("."))


_TOOL_FN_MAP = {
    "get_graph_schema": lambda args: get_graph_schema(),
    "validate_cypher": lambda args: validate_cypher(args["query"]),
    "run_cypher": lambda args: run_cypher(args["query"]),
}


def ask(question: str, max_iterations: int = 5) -> AgentResult:
    """Ask a natural language question; the agent translates it to Cypher and responds."""
    from rich.panel import Panel
    from rich.syntax import Syntax

    from src.common.llm import backend_for, get_client_and_model

    client, model = get_client_and_model("agent")
    agent_backend = backend_for("agent")
    messages = build_messages(question)
    cypher_attempts: list[dict] = []
    answer = ""

    console.print(Panel(f"[bold]{question}[/bold]", title=f"Question ({model})"))

    for iteration in range(1, max_iterations + 1):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOL_SPECS,
            tool_choice="auto",
            temperature=0,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            # Some OpenAI-compatible servers (e.g. vLLM without --enable-auto-tool-choice
            # --tool-call-parser) emit tool calls as raw text like
            # `[TOOL_CALLS][{"name":...}]` instead of structured tool_calls. Detect that so
            # the agent fails loudly instead of returning the raw marker as an "answer".
            if agent_backend == "local" and "[TOOL_CALLS]" in (msg.content or ""):
                raise RuntimeError(
                    "Agent backend 'local' returned tool calls as text, not structured "
                    "tool_calls. The vLLM server must be started with "
                    "`--enable-auto-tool-choice --tool-call-parser mistral` (for Pixtral). "
                    f"Raw content: {(msg.content or '')[:200]!r}"
                )
            answer = msg.content or ""
            messages.append({"role": "assistant", "content": answer})
            break

        # Append assistant message with tool calls
        messages.append(msg.model_dump(exclude_none=True))

        for tc in msg.tool_calls:
            fn_name = tc.function.name
            fn_args = json.loads(tc.function.arguments)

            result = _TOOL_FN_MAP[fn_name](fn_args)

            # Track Cypher attempts for tracing
            if fn_name in ("validate_cypher", "run_cypher"):
                query = fn_args.get("query", "")
                ok = result.get("ok", result.get("error") is None)
                error = result.get("error")
                rows = len(result.get("rows", []))
                cypher_attempts.append({"query": query, "ok": ok, "error": error, "rows": rows})

                label = "validate" if fn_name == "validate_cypher" else "run"
                status = "[green]OK[/green]" if ok else f"[red]{error}[/red]"
                console.print(
                    f"[dim][Iter {iteration}][/dim] [cyan]{label}[/cyan] "
                    f"→ {status} | rows={rows}"
                )
                console.print(Syntax(query, "cypher", theme="monokai", word_wrap=True))
            elif fn_name == "get_graph_schema":
                console.print(f"[dim][Iter {iteration}][/dim] get_graph_schema called")

            result_str = json.dumps(result, ensure_ascii=False)
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result_str,
            })
    else:
        answer = answer or "[Agent reached the iteration limit without a final answer]"

    # Persist trace
    TRACES_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    trace_path = TRACES_DIR / f"{timestamp}.json"
    trace_data = {
        "question": question,
        "cypher_attempts": cypher_attempts,
        "answer": answer,
        "messages": messages,
    }
    trace_path.write_text(json.dumps(trace_data, indent=2, ensure_ascii=False), encoding="utf-8")

    return AgentResult(answer=answer, cypher_attempts=cypher_attempts, trace_path=trace_path)
