#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

MASTER_URL="${MASTER_HTTP_URL:-http://localhost:8000}"
LEVELS="${LEVELS:-25}"
STRATEGIES="${STRATEGIES:-round_robin least_active load_aware lowest_latency}"

echo "Comparing scheduling strategies"
echo "Master: $MASTER_URL"
echo "Levels: $LEVELS"
echo

for strategy in $STRATEGIES; do
  echo "================================================================"
  echo "Strategy: $strategy"
  echo "================================================================"
  scripts/set-strategy.sh "$strategy"
  python3 scripts/send-project-requests.py \
    --master "$MASTER_URL" \
    --levels $LEVELS \
    --burst
  echo
done
