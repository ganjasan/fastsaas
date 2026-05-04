#!/usr/bin/env bash
# Bring up the FastSaaS dev stack (Postgres / Redis / Mailhog).
#
# FastSaaS dev ports = standard + 100:
#   postgres 5532, redis 6479, mailhog 1125 (SMTP) / 8125 (UI).
#
# Idempotent — re-running brings the stack to the desired state and waits
# for all services to be healthy before returning.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

docker compose up -d --wait

cat <<'EOF'

Dev stack up.

  Backend:    cd backend  && uv run uvicorn fastsaas.main:app --reload --port 8100
  Frontend:   cd frontend && npm run dev          (vite on :5273)
  Mailhog UI: http://localhost:8125
  Postgres:   localhost:5532  (user fastsaas / pw dev)
  Redis:      localhost:6479

Migrations:   make migrate     (alembic upgrade head against the dev DB)
Tear down:    make down        (stops services, deletes volumes)
EOF
