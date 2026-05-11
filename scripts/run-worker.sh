#!/usr/bin/env sh
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"

usage() {
  echo "Usage: $0 [MASTER_IP_OR_URL]"
  echo
  echo "Example:"
  echo "  $0"
  echo "  $0 192.168.1.10"
  echo "  $0 http://192.168.1.10:8000"
}

detect_lan_ip() {
  if command -v ipconfig >/dev/null 2>&1; then
    ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true
    return
  fi

  if command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | awk '{print $1}'
    return
  fi
}

if [ -f "$ROOT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT_DIR/.env"
  set +a
fi

MASTER_INPUT="${1:-${MASTER_HTTP_URL:-${MASTER_IP:-}}}"
if [ -z "$MASTER_INPUT" ]; then
  echo "No master address configured."
  echo
  echo "Either set MASTER_HTTP_URL in .env:"
  echo "  MASTER_HTTP_URL=http://192.168.1.10:8000"
  echo
  echo "Or pass it once:"
  echo "  $0 192.168.1.10"
  exit 1
fi

case "$MASTER_INPUT" in
  http://*|https://*) MASTER_HTTP_URL="$MASTER_INPUT" ;;
  *) MASTER_HTTP_URL="http://$MASTER_INPUT:${MASTER_HTTP_PORT:-8000}" ;;
esac

WORKER_ADVERTISE_HOST="${WORKER_ADVERTISE_HOST:-$(detect_lan_ip)}"
if [ -z "$WORKER_ADVERTISE_HOST" ]; then
  echo "Could not auto-detect this worker's LAN IP."
  echo "Run again with WORKER_ADVERTISE_HOST set, for example:"
  echo "  WORKER_ADVERTISE_HOST=192.168.1.23 $0"
  exit 1
fi

export MASTER_HTTP_URL
export WORKER_ADVERTISE_HOST

echo "Starting worker container"
echo "Master:      $MASTER_HTTP_URL"
echo "Worker IP:   $WORKER_ADVERTISE_HOST"
echo

cd "$ROOT_DIR"
exec docker compose -f docker-compose.worker.yml up --build -d
