"""Role-based, backend-agnostic LLM client selection.

Both the VLM extractor and the agent talk to an OpenAI-compatible Chat Completions API.
This module lets each *role* ("extraction", "agent") independently target either the
hosted OpenAI API (gpt-4o) or a local OpenAI-compatible server (e.g. vLLM serving
Pixtral). Selection is by environment variable so a notebook can set it once at the top:

    os.environ["EXTRACTION_BACKEND"] = "openai"   # or "local"
    os.environ["AGENT_BACKEND"]      = "openai"    # or "local"

Optional per-role model override: ``EXTRACTION_MODEL`` / ``AGENT_MODEL``.
Local server config: ``LOCAL_VLLM_BASE_URL`` / ``LOCAL_VLLM_MODEL`` / ``LOCAL_VLLM_API_KEY``.

Backward compatibility: with no env vars set, every role resolves to OpenAI ``gpt-4o`` —
identical to the previous hardcoded behaviour, so `tutorial.py` and the Part 2 notebook
are unaffected.
"""
from __future__ import annotations

import os

from src.common.config import get_secret

# Defaults for the local OpenAI-compatible (vLLM) server. The IP is a fallback for the
# course's UAB box; override via LOCAL_VLLM_BASE_URL (e.g. in .env) for any other host.
_LOCAL_BASE_URL_DEFAULT = "http://158.109.8.116:8000/v1"
_LOCAL_MODEL_DEFAULT = "mistralai/Pixtral-12B-2409"

_OPENAI_MODEL_DEFAULT = "gpt-4o"


def _resolve(role: str) -> tuple[str, str]:
    """Return (backend, model) for a role. backend in {"openai", "local"}."""
    role_u = role.upper()
    backend = os.environ.get(f"{role_u}_BACKEND", "openai").strip().lower()
    if backend in ("local", "vllm", "pixtral"):
        model = os.environ.get(f"{role_u}_MODEL") or os.environ.get(
            "LOCAL_VLLM_MODEL", _LOCAL_MODEL_DEFAULT
        )
        return "local", model
    # default / "openai" / "gpt" / "gpt-4o"
    model = os.environ.get(f"{role_u}_MODEL", _OPENAI_MODEL_DEFAULT)
    return "openai", model


def get_client_and_model(role: str):
    """Build an OpenAI-compatible client and pick the model for the given role.

    role: "extraction" or "agent".
    Returns (client, model_name). The client is the `openai.OpenAI` SDK pointed at
    either api.openai.com or the local vLLM server.
    """
    from openai import OpenAI

    backend, model = _resolve(role)
    if backend == "local":
        base_url = os.environ.get("LOCAL_VLLM_BASE_URL", _LOCAL_BASE_URL_DEFAULT)
        api_key = os.environ.get("LOCAL_VLLM_API_KEY", "EMPTY")  # vLLM ignores the value
        return OpenAI(base_url=base_url, api_key=api_key), model
    return OpenAI(api_key=get_secret("OPENAI_API_KEY")), model


def backend_for(role: str) -> str:
    """Return just the backend name ("openai" | "local") for a role."""
    return _resolve(role)[0]
