#!/usr/bin/env sh
set -eu

MASTER_URL="${MASTER_HTTP_URL:-http://localhost:8000}"
MASTER_URL="${MASTER_URL%/}"
INTERVAL="${INTERVAL:-2}"

echo "Fault tolerance demo watcher"
echo "Master: $MASTER_URL"
echo
echo "In another terminal, run load:"
echo "  python3 scripts/send-project-requests.py --levels 100 --ramp 30"
echo
echo "On one worker laptop, stop the worker:"
echo "  docker stop worker-agent"
echo
echo "Then restart it:"
echo "  docker start worker-agent"
echo
echo "This watcher prints worker status every ${INTERVAL}s. Press Ctrl+C to stop."
echo

while true; do
  date "+%H:%M:%S"
  curl -fsS "$MASTER_URL/workers" || true
  echo
  echo
  sleep "$INTERVAL"
done
