#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

echo "Starting master stack: nginx, master, Prometheus, Grafana"
echo
echo "Master API: http://localhost:${MASTER_HTTP_PORT:-8000}"
echo "Grafana:    http://localhost:${GRAFANA_PORT:-3000}"
echo
echo "Set MASTER_HTTP_URL in .env to this laptop's LAN IP for workers."
echo "macOS: ipconfig getifaddr en0"
echo "Linux: hostname -I"
echo "Example: MASTER_HTTP_URL=http://192.168.1.10:8000"
echo

cd "$ROOT_DIR"
exec docker compose up --build -d
