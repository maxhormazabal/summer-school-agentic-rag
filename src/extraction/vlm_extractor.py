from __future__ import annotations

import base64
import copy
import json
from pathlib import Path

from tenacity import retry, stop_after_attempt, wait_exponential

from src.common.config import get_secret
from src.common.logging import console
from src.ontology.schema import MatchExtraction


def _prepare_schema(schema: dict) -> dict:
    """Prepare a Pydantic JSON schema for OpenAI structured outputs strict mode.

    Two fixes are needed:
    1. $ref cannot have sibling keywords (e.g. description) — inline all $refs.
    2. Every property of every object must appear in required (even nullable ones).
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", {})

    def resolve(obj: object) -> object:
        if isinstance(obj, dict):
            # Inline $ref first
            if "$ref" in obj:
                ref_name = obj["$ref"].split("/")[-1]
                resolved = copy.deepcopy(defs.get(ref_name, {}))
                for k, v in obj.items():
                    if k != "$ref":
                        resolved[k] = v
                return resolve(resolved)
            # Recurse values
            result = {k: resolve(v) for k, v in obj.items()}
            # Ensure all properties are in required (OpenAI strict mode requirement)
            if "properties" in result and isinstance(result["properties"], dict):
                result["required"] = list(result["properties"].keys())
            return result
        if isinstance(obj, list):
            return [resolve(item) for item in obj]
        return obj

    return resolve(schema)  # type: ignore[return-value]

_SYSTEM_PROMPT = """\
You are an expert assistant specialised in extracting structured data from official football match \
reports of the Federació Catalana de Futbol (FCF). The reports are written in Catalan.

Structure of an FCF match report:
- Header: matchday (Jornada N), competition, status (ACTA TANCADA), home and away teams, final score.
- Per team: TITULARS (starters), SUPLENTS (substitutes) with jersey number and name; EQUIP TÈCNIC with role code.
- Centre: ÀRBITRES (referee and committee), GOLS (goal table with running score, scorer and minute), \
ESTADI (stadium and address).
- TARGETES: cards with colour (yellow/red), minute and recipient.

Interpretation rules:
- The running score in the GOLS table is the source of truth for goal order and the scoring team.
- An own goal may be indicated with a different icon; mark it as type="own".
- Cards can be issued to players (target_kind="player") or to coaching staff (target_kind="coach").
- Some names are single-word nicknames; do not assume "surname, first name" format.
- If a field is not visible or does not apply, use null.

Return ONLY the JSON that validates against the MatchExtraction schema, with no additional text.
"""


def _image_to_data_url(image_path: Path) -> str:
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:image/png;base64,{b64}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def extract(image_path: Path) -> MatchExtraction:
    """Extract structured match data from a PNG image using GPT-4o vision."""
    from pydantic import ValidationError

    from src.common.llm import get_client_and_model

    client, model = get_client_and_model("extraction")
    schema = _prepare_schema(MatchExtraction.model_json_schema())

    console.print(f"[cyan]VLM extracting {image_path.name} ({model})...[/cyan]")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_to_data_url(image_path), "detail": "high"},
                    },
                    {"type": "text", "text": "Extract all data from this match report in the specified JSON format."},
                ],
            },
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "MatchExtraction", "schema": schema, "strict": True},
        },
        temperature=0,
    )

    raw = response.choices[0].message.content
    try:
        return MatchExtraction.model_validate_json(raw)
    except ValidationError as exc:
        console.print(f"[red]Validation error for {image_path.name}: {exc}[/red]")
        raise
