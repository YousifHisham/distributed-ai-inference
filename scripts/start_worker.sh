#!/usr/bin/env bash
# Start a worker directly (no Docker) on a Thunder Compute instance.
#
# Usage:
#   ./scripts/start_worker.sh <master_url> <this_instance_public_ip>
#
# Example:
#   ./scripts/start_worker.sh https://yeast-spokesman-taekwondo.ngrok-free.app 216.81.200.241

set -e

MASTER_URL="${1:?Usage: $0 <master_url> <advertise_ip>}"
ADVERTISE_IP="${2:?Usage: $0 <master_url> <advertise_ip>}"

export MASTER_HTTP_URL="$MASTER_URL"
export WORKER_ADVERTISE_HOST="$ADVERTISE_IP"
export WORKER_HTTP_PORT="${WORKER_HTTP_PORT:-8001}"
export WORKER_MAX_SLOTS="${WORKER_MAX_SLOTS:-8}"
export OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
export WORKER_MODEL="${WORKER_MODEL:-llama3.2:1b}"
export HEARTBEAT_INTERVAL="${HEARTBEAT_INTERVAL:-2}"
export MOCK_GPU="${MOCK_GPU:-false}"
export RAG_DOCS_DIR="${RAG_DOCS_DIR:-rag/knowledge_base}"

echo "========================================="
echo " Worker startup"
echo "========================================="
echo "  Master URL   : $MASTER_HTTP_URL"
echo "  Advertise    : http://$ADVERTISE_IP:$WORKER_HTTP_PORT"
echo "  Max slots    : $WORKER_MAX_SLOTS"
echo "  Model        : $WORKER_MODEL"
echo "  Ollama       : $OLLAMA_URL"
echo "========================================="

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

pip install -q -r worker/requirements.txt

PYTHONPATH="$REPO_ROOT" python3 -m uvicorn worker.main:app \
    --host 0.0.0.0 \
    --port "$WORKER_HTTP_PORT" \
    --log-level info
