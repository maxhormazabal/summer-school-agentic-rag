#!/usr/bin/env bash
# Simulates the Google Colab experience locally.
#
# Creates a clean Python venv, installs only jupyter + nbconvert,
# then executes the full notebook with COLAB_SIMULATE=true so it
# self-installs all project dependencies from requirements.txt —
# exactly as it would in a fresh Colab runtime.
#
# System dependencies (poppler-utils, graphviz) must already be present
# on your machine (on macOS: brew install poppler graphviz).
#
# Usage:
#   export OPENAI_API_KEY="sk-..."
#   export NEO4J_URI="neo4j+s://..."
#   export NEO4J_USERNAME="neo4j"
#   export NEO4J_PASSWORD="..."
#   export NEO4J_DATABASE="neo4j"
#   ./scripts/test_colab.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.venv-colab-test"
OUT="$ROOT/tutorial_colab_test.ipynb"

# ── Validate required credentials ─────────────────────────────────────────────
for var in OPENAI_API_KEY NEO4J_URI NEO4J_PASSWORD; do
    if [[ -z "${!var:-}" ]]; then
        echo "ERROR: \$$var is not set. Export it before running this script."
        exit 1
    fi
done

# ── Create clean venv ─────────────────────────────────────────────────────────
echo "→ Creating clean test venv at $VENV"
uv venv --python 3.11 "$VENV"

# ── Install only the runner — nothing from the project yet ───────────────────
echo "→ Installing minimal runner (jupyter + nbconvert)"
uv pip install --python "$VENV/bin/python" jupyter nbconvert ipykernel

# ── Execute notebook ──────────────────────────────────────────────────────────
echo "→ Executing notebook with COLAB_SIMULATE=true ..."
cd "$ROOT"
COLAB_SIMULATE=true \
  "$VENV/bin/jupyter" nbconvert \
    --to notebook \
    --execute \
    --ExecutePreprocessor.timeout=600 \
    --output "$OUT" \
    tutorial.ipynb

echo ""
echo "✓ Done. Executed notebook saved to:"
echo "  $OUT"
