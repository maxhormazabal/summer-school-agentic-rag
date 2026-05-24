"""
Local VLM backend (Qwen3-VL-8B-Instruct via HuggingFace transformers).

Contract (mirrors src.extraction.vlm_extractor.extract):
    def extract(image_path: Path) -> MatchExtraction

Model is loaded lazily once per process (singleton) on the first CUDA device visible to the
process. Multi-GPU parallelism is achieved by spawning one worker process per GPU, each pinned
via CUDA_VISIBLE_DEVICES — see `scripts/bulk_extract_local.py`.

System prompt: reused verbatim from `src.extraction.vlm_extractor._SYSTEM_PROMPT`.

JSON validation: post-hoc with a self-correction loop. The model emits JSON, we try
`MatchExtraction.model_validate_json(raw)`, and on ValidationError we issue a follow-up turn
asking the model to fix the JSON given the validator error.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import Lock

from src.common.config import get_secret
from src.common.logging import console
from src.extraction.vlm_extractor import _SYSTEM_PROMPT
from src.ontology.schema import MatchExtraction

# Qwen3-VL tends to stop after the TITULARS column and omit the separate SUPLENTS
# block entirely (observed: ~92% of team-sides had zero subs in the first full run,
# vs 2-8 subs/team with GPT-4o). GPT-4o needs no such nudge; this emphasis is local
# to the Qwen backend and is appended to the shared _SYSTEM_PROMPT verbatim.
_SUPLENTS_EMPHASIS = (
    "\n\nCRITICAL: Each team has TWO player lists — TITULARS (starters) AND a "
    "separate SUPLENTS (substitutes) block, usually below or beside the starters. "
    "You MUST extract EVERY row of the SUPLENTS list as a lineup entry with "
    'role="sub". Do not stop after the starters. A team typically has several '
    "substitutes; returning zero substitutes is almost always an extraction error."
)
_SYSTEM_PROMPT_LOCAL = _SYSTEM_PROMPT + _SUPLENTS_EMPHASIS

DEFAULT_MODEL_ID = os.environ.get("VLM_LOCAL_MODEL_ID", "Qwen/Qwen3-VL-8B-Instruct")
DEFAULT_MAX_NEW_TOKENS = int(os.environ.get("VLM_LOCAL_MAX_NEW_TOKENS", "4096"))
DEFAULT_CORRECTION_ATTEMPTS = int(os.environ.get("VLM_LOCAL_CORRECTION_ATTEMPTS", "2"))

_MODEL = None
_PROCESSOR = None
_MODEL_LOCK = Lock()


def model_slug(model_id: str | None = None) -> str:
    """Return a filesystem-safe slug for a given HF model id."""
    mid = model_id or DEFAULT_MODEL_ID
    return mid.split("/", 1)[-1].lower().replace("_", "-")


def _strip_to_json(text: str) -> str:
    """Best-effort extraction of the outermost JSON object in a model reply."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    if "{" in text and "}" in text:
        text = text[text.index("{") : text.rindex("}") + 1]
    return text


def _repair_trailing_commas(text: str) -> str:
    """Strip commas that sit directly before a closing brace/bracket.

    Qwen3-VL deterministically emits a trailing comma on some reports (e.g. 75.png),
    which the strict JSON parser rejects and the self-correction loop reproduces. A
    trailing comma before `}`/`]` is never valid JSON, so removing it is a safe salvage.
    Applied only after a strict parse has already failed.
    """
    return re.sub(r",(\s*[}\]])", r"\1", text)


def _load() -> tuple[object, object]:
    """Lazy-load model+processor onto the local CUDA device."""
    global _MODEL, _PROCESSOR
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL, _PROCESSOR

        import torch  # heavy import — deferred
        from transformers import AutoModelForImageTextToText, AutoProcessor

        token = None
        try:
            token = get_secret("HF_TOKEN")
        except Exception:
            pass

        device_count = torch.cuda.device_count() if torch.cuda.is_available() else 0
        device = "cuda:0" if device_count else "cpu"
        dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32

        console.print(
            f"[cyan]Loading {DEFAULT_MODEL_ID} on {device} (dtype={dtype}, visible_gpus={device_count})[/cyan]"
        )

        kwargs = {"trust_remote_code": True}
        if token:
            kwargs["token"] = token

        _PROCESSOR = AutoProcessor.from_pretrained(DEFAULT_MODEL_ID, **kwargs)
        try:
            _MODEL = AutoModelForImageTextToText.from_pretrained(
                DEFAULT_MODEL_ID,
                dtype=dtype,
                device_map=device,
                **kwargs,
            )
        except TypeError:
            _MODEL = AutoModelForImageTextToText.from_pretrained(
                DEFAULT_MODEL_ID,
                torch_dtype=dtype,
                device_map=device,
                **kwargs,
            )
        _MODEL.eval()
        return _MODEL, _PROCESSOR


def _build_user_prompt() -> str:
    schema = json.dumps(MatchExtraction.model_json_schema(), ensure_ascii=False)
    return (
        "Extract all data from this FCF match report image. "
        "Return ONLY a single JSON object that validates against this schema, "
        "with no surrounding prose or markdown fences.\n\n"
        f"JSON schema:\n{schema}"
    )


def _chat(messages: list[dict]) -> str:
    """Run a single chat-completion turn against the local Qwen3-VL model."""
    import torch

    model, processor = _load()

    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)

    try:
        from qwen_vl_utils import process_vision_info
        image_inputs, video_inputs = process_vision_info(messages)
    except ImportError:
        from PIL import Image
        image_inputs = []
        for m in messages:
            content = m.get("content", [])
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image":
                    img_ref = part.get("image")
                    if isinstance(img_ref, (str, Path)):
                        image_inputs.append(Image.open(img_ref).convert("RGB"))
                    else:
                        image_inputs.append(img_ref)
        video_inputs = None

    inputs = processor(
        text=[text],
        images=image_inputs if image_inputs else None,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        generated = model.generate(
            **inputs,
            max_new_tokens=DEFAULT_MAX_NEW_TOKENS,
            do_sample=False,
        )
    trimmed = [out[len(inp) :] for inp, out in zip(inputs.input_ids, generated)]
    decoded = processor.batch_decode(trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return decoded[0]


def extract(image_path: Path) -> MatchExtraction:
    """Extract a `MatchExtraction` from one PNG using Qwen3-VL.

    Strategy: ask once, validate, self-correct up to DEFAULT_CORRECTION_ATTEMPTS times.
    """
    from pydantic import ValidationError

    image_path = Path(image_path)
    user_prompt = _build_user_prompt()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT_LOCAL},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(image_path)},
                {"type": "text", "text": user_prompt},
            ],
        },
    ]

    last_error: Exception | None = None
    last_raw: str = ""
    for attempt in range(DEFAULT_CORRECTION_ATTEMPTS + 1):
        raw = _chat(messages)
        last_raw = raw
        candidate = _strip_to_json(raw)
        try:
            return MatchExtraction.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc
            repaired = _repair_trailing_commas(candidate)
            if repaired != candidate:
                try:
                    return MatchExtraction.model_validate_json(repaired)
                except ValidationError:
                    pass
            if attempt >= DEFAULT_CORRECTION_ATTEMPTS:
                break
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Your JSON failed validation with the following errors. "
                        "Return ONLY a corrected JSON object — no prose, no fences.\n\n"
                        f"{exc}"
                    ),
                }
            )

    raise RuntimeError(
        f"Qwen3-VL output failed validation after {DEFAULT_CORRECTION_ATTEMPTS + 1} attempts. "
        f"Last error: {last_error}. Last raw (truncated): {last_raw[:500]!r}"
    )
