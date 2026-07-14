#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

HOST="${VIEWER_HOST:-127.0.0.1}"
PORT="${1:-${VIEWER_PORT:-8765}}"
URL="http://${HOST}:${PORT}/"

if command -v python >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON:-python}"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="${PYTHON:-python3}"
else
  echo "Python was not found. Please install Python or add it to PATH." >&2
  exit 1
fi

export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"

is_viewer_running() {
  "$PYTHON_BIN" - "$URL" <<'PY' >/dev/null 2>&1
import json
import sys
import urllib.request

base = sys.argv[1].rstrip("/")
with urllib.request.urlopen(base + "/api/health", timeout=0.5) as response:
    health = json.load(response)
with urllib.request.urlopen(base + "/api/session", timeout=0.5) as response:
    session = json.load(response)
raise SystemExit(0 if health.get("apiVersion") == 6 and session.get("token") else 1)
PY
}

is_port_occupied() {
  "$PYTHON_BIN" - "$URL" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

url = sys.argv[1].rstrip("/") + "/api/health"
with urllib.request.urlopen(url, timeout=0.5) as response:
    raise SystemExit(0 if response.status == 200 else 1)
PY
}

open_url() {
  if command -v cygstart >/dev/null 2>&1; then
    cygstart "$URL"
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$URL" >/dev/null 2>&1
  elif command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1
  else
    echo "Open this URL in your browser: $URL"
  fi
}

if is_viewer_running; then
  echo "Teacher viewer is already running: $URL"
  open_url
  exit 0
fi

if is_port_occupied; then
  echo "An older or incompatible viewer is already using $URL" >&2
  echo "Stop that viewer process, then run start_viewer.sh again." >&2
  exit 1
fi

echo "Starting teacher viewer: $URL"
"$PYTHON_BIN" tutor.py view --host "$HOST" --port "$PORT" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup INT TERM EXIT

for _ in $(seq 1 40); do
  if is_viewer_running; then
    open_url
    echo "Press Ctrl+C to stop the viewer server."
    wait "$SERVER_PID"
    exit $?
  fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    wait "$SERVER_PID"
    exit $?
  fi
  sleep 0.25
done

echo "Viewer server did not become ready in time." >&2
exit 1
