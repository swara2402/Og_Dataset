#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON:-$ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${PYTHON:-python3}"
fi
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python 3.12+ is required. Install Python, then retry." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required for local readiness checks." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Python 3.12+ is required." >&2
  exit 1
fi
if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
  echo "Node.js 20.19+ (or 22.12+) and npm are required for the frontend." >&2
  exit 1
fi
if ! node -e 'const [major, minor] = process.versions.node.split(".").map(Number); process.exit((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22 ? 0 : 1)'; then
  echo "Vite 8 requires Node.js 20.19+ or 22.12+." >&2
  exit 1
fi
if ! "$PYTHON_BIN" -c 'import fastapi, uvicorn, docx, pypdf, reportlab, jsonschema, multipart, pydantic_settings, httpx, markdown, bs4' >/dev/null 2>&1; then
  echo "Backend dependencies are missing. Run: $PYTHON_BIN -m pip install -r requirements.txt" >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "Frontend dependencies are missing. Run: cd frontend && npm ci" >&2
  exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  [[ -z "$FRONTEND_PID" ]] || kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -z "$BACKEND_PID" ]] || kill "$BACKEND_PID" 2>/dev/null || true
  [[ -z "$FRONTEND_PID" ]] || wait "$FRONTEND_PID" 2>/dev/null || true
  [[ -z "$BACKEND_PID" ]] || wait "$BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT
trap 'exit 130' INT TERM

"$PYTHON_BIN" -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
(
  cd "$ROOT/frontend"
  npm run dev -- --host 127.0.0.1 --strictPort
) &
FRONTEND_PID=$!

ready=0
for _ in {1..30}; do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null || ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "A local service exited during startup. Check the error above." >&2
    exit 1
  fi
  if curl --silent --fail http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 \
    && curl --silent --fail http://127.0.0.1:5173/ >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Local services did not become ready within 30 seconds." >&2
  exit 1
fi

echo
echo "Turnitout is running locally:"
echo "  App:    http://127.0.0.1:5173"
echo "  API:    http://127.0.0.1:8000/api/v1/health"
echo "  Docs:   http://127.0.0.1:8000/docs"
echo "  Offline: document processing stays on this machine."
echo "Press Ctrl+C to stop both services."
echo

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done
echo "A local service stopped. Shutting down the other service." >&2
exit 1
