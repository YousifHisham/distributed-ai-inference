#!/usr/bin/env sh
set -eu

MASTER_URL="${MASTER_HTTP_URL:-http://localhost:8000}"
MASTER_URL="${MASTER_URL%/}"
QUERY="${*:-Explain how fault tolerance works in this distributed LLM project.}"

python3 - "$MASTER_URL" "$QUERY" <<'PY'
import json
import sys
import urllib.request

master_url = sys.argv[1].rstrip("/")
query = sys.argv[2]
payload = json.dumps({"query": query}).encode("utf-8")
request = urllib.request.Request(
    f"{master_url}/infer",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)

print(f"Sending request to {master_url}/infer")
print(f"Query: {query}")
print()

with urllib.request.urlopen(request, timeout=300) as response:
    data = json.loads(response.read().decode("utf-8"))

print(json.dumps(data, indent=2))
PY
