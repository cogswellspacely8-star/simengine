#!/usr/bin/env bash
# SimEngine fast launch — start the local server if it isn't already running,
# wait until it's ready, then open the UI in your browser. No terminal needed.

REPO="$(cd "$(dirname "$0")" && pwd)"
URL="http://localhost:8420"

# Already up? Just open it.
if ! curl -s --max-time 2 "$URL/api/domains" >/dev/null 2>&1; then
  cd "$REPO/v3" || exit 1
  # Keep the local model warm between calls; log to /tmp for troubleshooting.
  SIMENGINE_OLLAMA_KEEP_ALIVE=30m nohup python3 server.py >/tmp/simengine.log 2>&1 &
  # Wait up to ~15s for it to accept connections.
  for _ in $(seq 1 30); do
    curl -s --max-time 1 "$URL/api/domains" >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

xdg-open "$URL" >/dev/null 2>&1 || true
