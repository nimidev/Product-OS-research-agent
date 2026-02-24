#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing python at $VENV_PYTHON"
  echo "Create the virtualenv and install deps first."
  exit 1
fi

echo "== US-003 E2E runbook (Monday -> sync -> checkpoint -> UI chat) =="
echo
echo "1) Ensure infrastructure is running:"
echo "   docker-compose up qdrant -d"
echo
echo "2) Start API (separate terminal):"
echo "   $VENV_PYTHON -m research_agent serve"
echo
echo "3) Configure Monday integration (example request):"
cat <<'EOF'
curl -X PUT "http://localhost:8000/integrations/monday" \
  -H "Content-Type: application/json" \
  -d '{
    "enabled": true,
    "api_key": "YOUR_MONDAY_API_KEY",
    "board_ids": ["1234567890"],
    "entity_mappings": {"1234567890": "feature_request"},
    "sync_interval_seconds": 7200
  }'
EOF
echo
echo "4) Optional: test Monday connection:"
cat <<'EOF'
curl -X POST "http://localhost:8000/integrations/monday/test" \
  -H "Content-Type: application/json" \
  -d '{}'
EOF
echo
echo "5) Run sync:"
echo "   $VENV_PYTHON -m research_agent sync"
echo
echo "6) Run checkpoint gate:"
echo "   $ROOT_DIR/scripts/checkpoint_us003.sh"
echo
echo "7) Start UI (separate terminal):"
echo "   cd $ROOT_DIR/ui && npm install && npm run dev"
echo
echo "8) Verify chat in UI:"
echo "   - Ask a Monday-related question"
echo "   - Confirm answer/references are Monday-backed"
