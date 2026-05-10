#!/usr/bin/env sh
set -eu

DELAY_SECONDS="${1:-10}"
RESTART_AFTER_SECONDS="${2:-}"
CONTAINER_NAME="${WORKER_CONTAINER_NAME:-worker-agent}"

echo "Fault injection: worker shutdown during active requests"
echo "Container: $CONTAINER_NAME"
echo "Stop after: ${DELAY_SECONDS}s"

if [ -n "$RESTART_AFTER_SECONDS" ]; then
  echo "Restart after stop: ${RESTART_AFTER_SECONDS}s"
fi

echo
echo "Start load from the master first, for example:"
echo "  ./scripts/scenario.sh fault-load"
echo
echo "Waiting..."
sleep "$DELAY_SECONDS"

echo "Stopping $CONTAINER_NAME"
docker stop "$CONTAINER_NAME"

if [ -n "$RESTART_AFTER_SECONDS" ]; then
  echo "Waiting ${RESTART_AFTER_SECONDS}s before restart..."
  sleep "$RESTART_AFTER_SECONDS"
  echo "Restarting $CONTAINER_NAME"
  docker start "$CONTAINER_NAME"
fi

echo "Done"
