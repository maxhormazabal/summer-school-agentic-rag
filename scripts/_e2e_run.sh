#!/usr/bin/env bash
# TEMPORARY: execute a notebook top-to-bottom against local Neo4j + real OpenAI, as a
# faithful "runs in Colab" proxy. Local Dev mode (no COLAB_SIMULATE) → bootstrap cell only
# sets sys.path; credential cell skips placeholders so our exported env wins.
set -euo pipefail
cd "$(dirname "$0")/.."

# Credentials come from .env (cloud AuraDB + OpenAI) — same path as Colab uses get_secret().
# The notebook credential cell skips its placeholders, so these .env values win via get_secret.
export OPENAI_API_KEY="$(grep -E '^OPENAI_API_KEY=' .env | cut -d= -f2-)"
# gdown CLI for the Part 2 download cell
export PATH="$PWD/.venv/bin:$PATH"

NB="${1:?usage: _e2e_run.sh <notebook.ipynb>}"
OUTNAME="$(basename "${NB%.ipynb}")_executed"          # never touch the distributed notebook
echo ">>> executing $NB → /tmp/$OUTNAME.ipynb"
./.venv/bin/jupyter nbconvert --to notebook --execute \
  --ExecutePreprocessor.timeout=1200 \
  --ExecutePreprocessor.kernel_name=ss-venv \
  --output-dir /tmp --output "$OUTNAME" "$NB"
echo ">>> OK: $NB executed top-to-bottom with no errors (output: /tmp/$OUTNAME.ipynb)"
