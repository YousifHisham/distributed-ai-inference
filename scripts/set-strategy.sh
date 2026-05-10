#!/usr/bin/env sh
set -eu

MASTER_URL="${MASTER_HTTP_URL:-http://localhost:8000}"
MASTER_URL="${MASTER_URL%/}"
STRATEGY="${1:-load_aware}"

case "$STRATEGY" in
  round_robin|least_active|load_aware|lowest_latency) ;;
  *)
    echo "Invalid strategy: $STRATEGY"
    echo "Use: round_robin | least_active | load_aware | lowest_latency"
    exit 1
    ;;
esac

python3 - "$MASTER_URL" "$STRATEGY" <<'PY'
import json
import sys
import urllib.request

master_url = sys.argv[1].rstrip("/")
strategy = sys.argv[2]
payload = json.dumps({"strategy": strategy}).encode("utf-8")
request = urllib.request.Request(
    f"{master_url}/config/strategy",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

with urllib.request.urlopen(request, timeout=30) as response:
    print(response.read().decode("utf-8"))
PY

