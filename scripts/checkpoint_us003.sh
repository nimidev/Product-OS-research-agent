#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTEST="$ROOT_DIR/.venv/bin/pytest"

if [[ ! -x "$VENV_PYTEST" ]]; then
  echo "Missing pytest at $VENV_PYTEST"
  echo "Create the virtualenv and install deps first."
  exit 1
fi

echo "Running US-003 checkpoint tests (API + MCP Monday search)..."
"$VENV_PYTEST" "$ROOT_DIR/tests/test_us003_checkpoint.py" -q

echo "US-003 checkpoint passed."
