#!/usr/bin/env bash
# Start the FULL live demo with one command: pipeline API (:8000) + web UI (:5173).
# The demo API is the Python FastAPI app in apps/worker — NOT apps/api, which is the
# empty Phase-1 portal-backend placeholder.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -x apps/worker/.venv/bin/uvicorn ]; then
  echo "worker venv missing — one-time setup:"
  echo "  cd apps/worker && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'"
  exit 1
fi
if [ ! -d apps/web/node_modules ]; then
  echo "web deps missing — one-time setup:  cd apps/web && pnpm install"
  exit 1
fi

(cd apps/worker && .venv/bin/uvicorn case_prep.server:app --port 8000 --app-dir src) &
API_PID=$!
trap 'kill $API_PID 2>/dev/null' EXIT INT TERM
echo "pipeline API  -> http://localhost:8000  (pid $API_PID)"
echo "demo UI       -> http://localhost:5173"
cd apps/web && pnpm dev
