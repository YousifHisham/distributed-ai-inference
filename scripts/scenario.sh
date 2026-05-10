#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR"

scenario="${1:-help}"
shift || true

usage() {
  cat <<'EOF'
Usage: ./scripts/scenario.sh SCENARIO [args]

Core run commands:
  master            Start nginx + master + Prometheus + Grafana
  worker            Start this laptop as a worker

Project PDF scenarios:
  status            Show master health and registered workers
  rag               Send one RAG inference request
  load-small        Send a small rehearsal load: 10, 25, 50 users
  load-pdf          Send PDF load levels: 100, 500, 1000 users
  fault-watch       Watch worker health while you stop/restart a worker
  fault-load        Run a fault-demo load over 30 seconds
  fault-down [s]    Stop this worker after s seconds; default: 10
  fault-restart [s] [r]
                    Stop this worker after s seconds, restart after r seconds
  strategies        Compare all scheduling strategies
  strategy NAME     Switch strategy: round_robin, least_active, load_aware, lowest_latency

Worker controls:
  stop-worker       Stop local worker container
  start-worker      Start local worker container
  restart-worker    Restart local worker container

Examples:
  ./scripts/scenario.sh master
  ./scripts/scenario.sh worker
  ./scripts/scenario.sh rag
  ./scripts/scenario.sh strategy round_robin
  ./scripts/scenario.sh load-pdf
EOF
}

case "$scenario" in
  master)
    exec ./scripts/run-master.sh
    ;;
  worker)
    exec ./scripts/run-worker.sh "$@"
    ;;
  status)
    exec ./scripts/check-cluster.sh "$@"
    ;;
  rag)
    exec ./scripts/demo-request.sh "$@"
    ;;
  load-small)
    exec python3 scripts/send-project-requests.py --levels 10 25 50 --burst "$@"
    ;;
  load-pdf)
    exec ./scripts/run-pdf-load-demo.sh
    ;;
  fault-watch)
    exec ./scripts/fault-demo.sh
    ;;
  fault-load)
    exec python3 scripts/send-project-requests.py --levels 100 --ramp 30 "$@"
    ;;
  fault-down)
    exec ./scripts/down-worker-mid-requests.sh "${1:-10}"
    ;;
  fault-restart)
    exec ./scripts/down-worker-mid-requests.sh "${1:-10}" "${2:-15}"
    ;;
  strategy)
    exec ./scripts/set-strategy.sh "${1:-load_aware}"
    ;;
  strategies)
    exec ./scripts/compare-strategies.sh
    ;;
  stop-worker)
    exec docker stop worker-agent
    ;;
  start-worker)
    exec docker start worker-agent
    ;;
  restart-worker)
    docker stop worker-agent || true
    exec docker start worker-agent
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown scenario: $scenario"
    echo
    usage
    exit 1
    ;;
esac
