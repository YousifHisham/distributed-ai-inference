#!/usr/bin/env sh
set -eu

MASTER_URL="${1:-${MASTER_HTTP_URL:-http://localhost:8000}}"
MASTER_URL="${MASTER_URL%/}"

echo "Checking cluster at $MASTER_URL"
echo

echo "Master health:"
curl -fsS "$MASTER_URL/health"
echo
echo

echo "Registered workers:"
curl -fsS "$MASTER_URL/workers"
echo
echo

echo "Grafana:    http://localhost:${GRAFANA_PORT:-3000}"
echo "Prometheus: http://localhost:${PROMETHEUS_PORT:-9090}"
