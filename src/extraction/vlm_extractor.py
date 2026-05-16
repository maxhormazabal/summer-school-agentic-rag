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
Eres un asistente experto en extraer datos estructurados de actas oficiales de partidos de fútbol \
de la Federació Catalana de Futbol (FCF). Las actas están escritas en catalán.

Estructura de un acta FCF:
- Cabecera: jornada (Jornada N), competición, estado (ACTA TANCADA), equipos local y visitante, marcador final.
- Por equipo: TITULARS (titulares), SUPLENTS (suplentes) con dorsal y nombre; EQUIP TÈCNIC con código de rol.
- Centro: ÀRBITRES (árbitro y comité), GOLS (tabla de goles con marcador parcial creciente, autora y minuto), \
ESTADI (estadio y dirección).
- TARGETES: tarjetas con color (amarilla/roja), minuto y receptor.

Reglas de interpretación:
- El marcador parcial de la tabla GOLS es la fuente de verdad para el orden y el equipo que marcó.
- Un gol en propia puerta (gol en contra) puede indicarse con un icono diferente; márcalo como type="own".
- Las tarjetas pueden ser a jugadoras (target_kind="player") o a miembros del cuerpo técnico (target_kind="coach").
- Algunos nombres son apodos de una sola palabra; no asumas formato "apellido, nombre".
- Si un campo no es visible o no aplica, usa null.

Devuelve ÚNICAMENTE el JSON que valide contra el schema MatchExtraction, sin texto adicional.
"""


def _image_to_data_url(image_path: Path) -> str:
    data = image_path.read_bytes()
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:image/png;base64,{b64}"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def extract(image_path: Path) -> MatchExtraction:
    """Extract structured match data from a PNG image using GPT-4o vision."""
    from openai import OpenAI
    from pydantic import ValidationError

    client = OpenAI(api_key=get_secret("OPENAI_API_KEY"))
    schema = _prepare_schema(MatchExtraction.model_json_schema())

    console.print(f"[cyan]VLM extracting {image_path.name}...[/cyan]")
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": _image_to_data_url(image_path), "detail": "high"},
                    },
                    {"type": "text", "text": "Extrae todos los datos de esta acta en el formato JSON indicado."},
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
