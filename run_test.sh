#!/usr/bin/env bash
# Run integration-touching tests against an isolated stack.
#
# FastSaaS test ports = standard + 200 (vs. dev which is +100):
#   postgres 5632, redis 6579, mailhog 1225 (SMTP) / 8225 (UI).
#
# Why a separate stack? Some fixtures (e.g. clean_identity) wipe
# `actors` between tests via the migrator role; running tests against the
# dev stack would erase whatever you were poking at by hand. The compose
# project name "fastsaas-test" gives us isolated networks, volumes, and
# container names so the dev stack can keep running in parallel.
#
# Usage:
#   ./run_test.sh                 # apply migrations + full pytest
#   ./run_test.sh tests/test_foo  # forward args to pytest
#   ./run_test.sh --keep-stack    # run + leave the stack up afterwards
#   KEEP_STACK=1 ./run_test.sh    # same, via env
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PROJECT="fastsaas-test"
COMPOSE_FILE="docker-compose.test.yml"

# --- Parse our own flag, forward the rest to pytest ----------------------
KEEP_STACK="${KEEP_STACK:-0}"
PYTEST_ARGS=()
for arg in "$@"; do
  if [[ "$arg" == "--keep-stack" ]]; then
    KEEP_STACK=1
  else
    PYTEST_ARGS+=("$arg")
  fi
done

# --- Test-stack URLs (port shift +200) ------------------------------------
export DATABASE_URL="postgresql+asyncpg://app_user:dev@localhost:5632/fastsaas"
export DATABASE_URL_MIGRATOR="postgresql+asyncpg://alembic_migrator:dev@localhost:5632/fastsaas"
export REDIS_URL="redis://localhost:6579/0"
export SMTP_HOST="localhost"
export SMTP_PORT="1225"
export MAILHOG_HTTP_URL="http://localhost:8225"
export APP_URL="http://localhost:5273"   # tests render magic-link URLs; reuse dev value
# ENV stays "dev" (the Settings default): cookie Secure flag is gated on
# `settings.env != "dev"`, and pytest's ASGITransport speaks http://, so
# Secure cookies would never round-trip and refresh-rotation tests would 401.

# --- Bring stack up + wait ------------------------------------------------
echo "[run_test] starting test stack (project=$PROJECT)"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d --wait

# --- Apply migrations against the test DB --------------------------------
echo "[run_test] alembic upgrade head"
(cd backend && uv run alembic upgrade head)

# --- Run pytest -----------------------------------------------------------
set +e
(cd backend && uv run pytest "${PYTEST_ARGS[@]}")
status=$?
set -e

# --- Tear down (unless explicitly preserved) -----------------------------
if [[ "$KEEP_STACK" -eq 1 ]]; then
  echo "[run_test] keeping stack up (project=$PROJECT). Stop manually with:"
  echo "          docker compose -p $PROJECT -f $COMPOSE_FILE down -v"
else
  echo "[run_test] tearing down stack (project=$PROJECT)"
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v >/dev/null
fi

exit $status
