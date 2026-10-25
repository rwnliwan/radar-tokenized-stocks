#!/bin/bash
# Server-boot test: start Streamlit headless, curl localhost, kill by PID.
# Usage: bash tests_fase2/server_boot.sh
set -u
ROOT="/home/hatch/workspace/radar-tokenized-stocks"
PORT=8502
LOG=/tmp/radar_dash_boot.log
BODY=/tmp/radar_dash_body.html
"$ROOT/.venv/bin/streamlit" run "$ROOT/dashboard/app.py" \
  --server.headless true --server.port "$PORT" --server.runOnSave false \
  > "$LOG" 2>&1 &
PID=$!
echo "streamlit pid: $PID"
for i in $(seq 1 30); do
  sleep 2
  if curl -s -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then
    break
  fi
done
curl -s -o "$BODY" -w "HTTP:%{http_code}\n" "http://localhost:$PORT/"
echo "body contains 'streamlit': $(grep -c -i streamlit "$BODY" || true) matches"
echo "--- server log (first 20 lines) ---"
head -20 "$LOG"
kill "$PID" 2>/dev/null
wait "$PID" 2>/dev/null
echo "server stopped (pid $PID killed)"
