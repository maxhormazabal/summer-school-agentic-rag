"""One-off probe: does emphasizing SUPLENTS recover the dropped substitutes?

Runs Qwen3-VL on data/images_full/10.png twice — current system prompt vs an
emphasized variant — and prints starter/sub counts per team for each.
Throwaway diagnostic; safe to delete.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extraction import vlm_local as V
from src.extraction.vlm_extractor import _SYSTEM_PROMPT
from src.ontology.schema import MatchExtraction

IMG = Path("data/images_full/10.png")

EMPHASIS = (
    _SYSTEM_PROMPT
    + "\n\nCRITICAL: Each team has TWO player lists — TITULARS (starters) AND a "
    "separate SUPLENTS (substitutes) block, usually below or beside the starters. "
    "You MUST extract EVERY row of the SUPLENTS list as a lineup entry with "
    'role="sub". Do not stop after the starters. A team typically has several '
    "substitutes; returning zero substitutes is almost always an extraction error."
)


def counts(m: MatchExtraction) -> str:
    out = []
    for side in ("home", "away"):
        team = getattr(m, side)
        roles = [e.role for e in team.lineup]
        st = sum(1 for r in roles if str(r).endswith("starter"))
        sb = sum(1 for r in roles if str(r).endswith("sub"))
        out.append(f"{side}: starters={st} subs={sb}")
    return " | ".join(out)


def run_with_system(system_prompt: str) -> MatchExtraction:
    from pydantic import ValidationError

    user_prompt = V._build_user_prompt()
    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": str(IMG)},
                {"type": "text", "text": user_prompt},
            ],
        },
    ]
    for attempt in range(V.DEFAULT_CORRECTION_ATTEMPTS + 1):
        raw = V._chat(messages)
        cand = V._strip_to_json(raw)
        try:
            return MatchExtraction.model_validate_json(cand)
        except ValidationError as exc:
            if attempt >= V.DEFAULT_CORRECTION_ATTEMPTS:
                raise
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Fix the JSON. Errors:\n{exc}"})


print("=== current prompt ===", flush=True)
print(counts(run_with_system(_SYSTEM_PROMPT)), flush=True)
print("=== emphasized SUPLENTS prompt ===", flush=True)
print(counts(run_with_system(EMPHASIS)), flush=True)
