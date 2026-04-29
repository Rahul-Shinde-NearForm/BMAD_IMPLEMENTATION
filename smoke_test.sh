#!/usr/bin/env zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

PYTHON="./.venv/bin/python"
PYTEST="./.venv/bin/pytest"

if [[ ! -x "$PYTHON" ]]; then
  echo "Error: Python virtual environment not found at $PYTHON"
  exit 1
fi

echo "[1/5] Applying migrations..."
"$PYTHON" backend/manage.py migrate >/dev/null

echo "[2/5] Starting Django server..."
"$PYTHON" backend/manage.py runserver 127.0.0.1:8000 >/tmp/opd_smoke_server.log 2>&1 &
SERVER_PID=$!

cleanup() {
  if ps -p "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

for _ in {1..20}; do
  if curl -sf http://127.0.0.1:8000/health/ >/dev/null; then
    break
  fi
  sleep 0.5
done

echo "[3/5] Verifying health endpoint..."
HEALTH_RESPONSE=$(curl -sSf http://127.0.0.1:8000/health/)
echo "Health: $HEALTH_RESPONSE"

echo "[4/5] Running tests..."
"$PYTEST" -q

echo "[5/5] Smoke test complete: PASS"
