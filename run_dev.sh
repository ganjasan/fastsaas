#!/usr/bin/env bash
# Bring up the FastSaaS dev environment end-to-end:
#   1. Postgres / Redis / Mailhog via docker compose (host ports +100).
#   2. Alembic migrations on the dev DB.
#   3. Backend uvicorn on :8100 (auto-reload).
#   4. Frontend Vite on :5273.
#
# Backend + frontend run in the background; their logs are streamed to the
# foreground prefixed with [backend]/[frontend]. Hit Ctrl+C once and the
# script tears down both processes (the docker stack stays up — use
# `make down` or `./run_dev.sh --shutdown` to stop it).
#
# Usage:
#   ./run_dev.sh                bring everything up, stream logs
#   ./run_dev.sh --no-migrate   skip alembic upgrade (assumes DB already at head)
#   ./run_dev.sh --shutdown     stop docker compose services + remove volumes
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

NO_MIGRATE=0
for arg in "$@"; do
  case "$arg" in
    --no-migrate) NO_MIGRATE=1 ;;
    --shutdown)
      echo "[run_dev] tearing down docker compose stack"
      docker compose down -v
      exit 0
      ;;
    *)
      echo "Unknown flag: $arg" >&2
      exit 2
      ;;
  esac
done

# ─── Docker stack ────────────────────────────────────────────────────────────
echo "[run_dev] bringing up Postgres / Redis / Mailhog"
docker compose up -d --wait

# ─── Migrations ──────────────────────────────────────────────────────────────
if [[ "$NO_MIGRATE" -eq 0 ]]; then
  echo "[run_dev] alembic upgrade head"
  (cd backend && uv run alembic upgrade head)
fi

# ─── Process orchestration ───────────────────────────────────────────────────
LOG_DIR="$(mktemp -d -t fastsaas-dev.XXXXXX)"
BACKEND_LOG="${LOG_DIR}/backend.log"
FRONTEND_LOG="${LOG_DIR}/frontend.log"

PIDS=()

cleanup() {
  echo
  echo "[run_dev] shutting down backend + frontend processes"
  # Use the process group on each child so any spawned grandchildren
  # (uvicorn workers, vite's esbuild helper) go down too.
  for pid in "${PIDS[@]:-}"; do
    [[ -n "${pid:-}" ]] || continue
    if kill -0 "$pid" 2>/dev/null; then
      pkill -P "$pid" 2>/dev/null || true
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
  echo "[run_dev] logs preserved at $LOG_DIR"
  echo "          docker stack still up (./run_dev.sh --shutdown to stop it)"
}
trap cleanup INT TERM EXIT

stream_with_prefix() {
  # $1 = label, $2 = log file path. Tails the file forever, prefixing each
  # line. The tailer is killed by the trap when the script exits.
  local label="$1" file="$2"
  : > "$file"
  ( tail -F "$file" 2>/dev/null | sed -u "s|^|[$label] |" ) &
  PIDS+=("$!")
}

start_backend() {
  ( cd backend && uv run uvicorn fastsaas.main:app --reload --port 8100 ) \
    >"$BACKEND_LOG" 2>&1 &
  PIDS+=("$!")
}

start_frontend() {
  ( cd frontend && npm run dev ) >"$FRONTEND_LOG" 2>&1 &
  PIDS+=("$!")
}

stream_with_prefix backend "$BACKEND_LOG"
stream_with_prefix frontend "$FRONTEND_LOG"
start_backend
start_frontend

cat <<EOF

[run_dev] dev stack is live.

  Frontend:    http://localhost:5273
  Backend:     http://localhost:8100  (health: /health, openapi: /openapi.json)
  Mailhog UI:  http://localhost:8125
  Postgres:    localhost:5532  (user fastsaas / pw dev)
  Redis:       localhost:6479

Logs streaming below — Ctrl+C to stop backend + frontend.
docker stack is left running (./run_dev.sh --shutdown to tear it down).

EOF

# Block until any of the long-running children exits, then trap fires cleanup.
wait -n
