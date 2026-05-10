#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

MASTER_URL="${MASTER_HTTP_URL:-http://localhost:8000}"

exec python3 scripts/send-project-requests.py \
  --master "$MASTER_URL" \
  --levels 100 500 1000 \
  --burst
