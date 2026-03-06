#!/usr/bin/env bash
# Reset local Research Agent state for retesting setup from scratch.
# Run from repo root: ./scripts/reset_local.sh [--full]
#
# Removes: qdrant_data/, database file, optionally .env (--full).
# After --full, run: python -m research_agent setup

set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

DB_NAME="research_agent.db"
if [[ -f .env ]]; then
  if grep -q '^DATABASE_PATH=' .env 2>/dev/null; then
    DB_NAME=$(grep '^DATABASE_PATH=' .env | cut -d= -f2- | tr -d '"' | tr -d "'" | xargs)
  fi
fi
DB_PATH="$ROOT/$DB_NAME"
QDRANT_DIR="$ROOT/qdrant_data"

echo "Resetting local state (repo root: $ROOT)"
echo ""

removed=0
if [[ -d "$QDRANT_DIR" ]]; then
  rm -rf "$QDRANT_DIR"
  echo "  removed: qdrant_data/"
  removed=1
fi
if [[ -f "$DB_PATH" ]]; then
  rm -f "$DB_PATH"
  echo "  removed: $DB_NAME"
  removed=1
fi

if [[ "$1" == "--full" ]]; then
  if [[ -f "$ROOT/.env" ]]; then
    rm -f "$ROOT/.env"
    echo "  removed: .env"
    removed=1
  fi
  echo ""
  echo "Full reset done. Run: python -m research_agent setup"
else
  echo ""
  echo "Data reset done. .env kept (use --full to remove and re-enter API key)."
fi

if [[ $removed -eq 0 ]]; then
  echo "  (nothing to remove)"
fi
echo ""
echo "Tip: In the browser, clear localStorage for localhost (or do a hard refresh)"
echo "     so the onboarding wizard shows again instead of the dashboard."
