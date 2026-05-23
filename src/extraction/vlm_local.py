"""
Local VLM backend stub — to be implemented when running on a GPU server.

CONTRACT (mirrors src.extraction.vlm_extractor.extract):
    def extract(image_path: Path) -> MatchExtraction

The function must:
1. Open the PNG at `image_path`.
2. Send it to a locally-hosted vision-language model.
3. Coerce the model's output into JSON that validates against `MatchExtraction`.
4. Return the parsed `MatchExtraction` instance.

SUGGESTED IMPLEMENTATIONS (pick one on the server, no preference enforced):
- **Qwen2-VL-7B-Instruct** via `transformers` — solid open-weight VLM, supports JSON-mode prompting.
- **InternVL2** — competitive on document understanding benchmarks.
- **Pixtral-12B** via vLLM — fast inference if you have ≥24 GB VRAM.
- **LLaVA-NeXT** family — well-supported, lots of integrations.

System prompt: REUSE `src.extraction.vlm_extractor._SYSTEM_PROMPT` verbatim — the prompt has
been tuned over the 3 example PDFs and should transfer to other open VLMs. It is in English
and describes the FCF report layout in detail.

JSON schema: import `MatchExtraction.model_json_schema()` and pass it (or a string description)
to the model. Open VLMs generally do not support OpenAI's `response_format=json_schema strict`,
so prefer constrained decoding (Outlines, lm-format-enforcer) OR a post-hoc validation +
self-correction loop:
    1. Ask the model to emit JSON.
    2. Try `MatchExtraction.model_validate_json(raw)`.
    3. On ValidationError, ask the model to fix the JSON given the validation error message.
    4. Retry up to N times.

Keep this function thread-safe-OR set workers=1 in bulk_extract.py (local GPU usually wants 1).

Until implemented, this stub raises NotImplementedError. The bulk script will catch it and
abort cleanly, telling the operator what to do.
"""
from __future__ import annotations

from pathlib import Path

from src.ontology.schema import MatchExtraction


def extract(image_path: Path) -> MatchExtraction:  # noqa: ARG001
    raise NotImplementedError(
        "Local VLM backend not implemented yet. See module docstring for the contract. "
        "Implement here, then run `bulk_extract.py --provider local`."
    )
