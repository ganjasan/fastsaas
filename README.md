# FastSaaS

Open-source fullstack SaaS starter-kit (FastAPI + React + Vite + TanStack + shadcn/ui).

Built around an **Actor-Centric identity model** (HUMAN / AGENT / SERVICE), strict tenant isolation via Postgres RLS, **capability-based access** with named role bundles, an immortal audit log, and a phased design system that turns into per-org branding.

## Quick start

```bash
cp .env.example .env            # defaults work out of the box
./run_dev.sh                    # docker compose up: Postgres / Redis / Mailhog
make migrate                    # alembic upgrade head
cd backend && uv run uvicorn fastsaas.main:app --reload --port 8100   # backend
cd frontend && npm run dev                                            # frontend (vite on :5273)
```

Open `http://localhost:5273`. Register, click the verification link from Mailhog (http://localhost:8125), sign in — fresh clone to logged-in `/auth/me` in well under 15 minutes.

### Host-port convention

FastSaaS shifts every host-side port by a fixed offset so multiple SaaS-stack projects coexist locally. Container-internal ports are unchanged.

| | standard | **dev** (`+100`) | **test** (`+200`) |
|---|---|---|---|
| Postgres | 5432 | 5532 | 5632 |
| Redis | 6379 | 6479 | 6579 |
| Mailhog SMTP / UI | 1025 / 8025 | 1125 / 8125 | 1225 / 8225 |
| FastAPI | 8000 | 8100 | — |
| Vite | 5173 | 5273 | — |

- `./run_dev.sh` — dev stack (`docker-compose.yml`, project `fastsaas`).
- `./run_test.sh [pytest args]` — isolated test stack (`docker-compose.test.yml`, project `fastsaas-test`, own volumes), applies migrations and runs pytest. Add `--keep-stack` or `KEEP_STACK=1` to leave the stack running after the run.

CI uses standard ports — clean runners have nothing to conflict with.

## Repo layout

| Path | What lives there |
|---|---|
| `backend/` | FastAPI app. Identity layer at `src/fastsaas/identity/`. |
| `frontend/` | React 18 + TanStack Router. Auth feature at `src/features/auth/`. |
| `docs/runbooks/` | Operational runbooks (e.g. `rotate-jwt-keys.md`). |
| `infra/dev-secrets/` | DEV-ONLY committed secrets (JWT keypair, Postgres init). |
| `requirements/` | Wiegers vision, formal use cases, ADRs, research notes. |
| `openspec/` | OpenSpec change proposals + completed specs. |

## Auth in dev

Sign-in works the same in dev as in prod — only the toolchain you can poke at differs.

- **Mailhog** captures every outbound email at `http://localhost:8125`. Verification, magic-link, and password-reset messages land there; the link in the body is the same one a prod user would see.
- **Dev OAuth bypass** — set `OAUTH_DEV_BYPASS=true` in `.env` and the backend exposes `GET /auth/oauth/dev/start?email=<addr>` which skips the provider round-trip and signs you in directly. Returns 404 when the env is unset.
- **JWT dev keypair** — `infra/dev-secrets/jwt/dev-1.{pem,pub.pem}` is committed as a DEV-ONLY keypair so a clean clone reaches a logged-in `/auth/me` without further setup. Regenerate with `make gen-jwt-keys`. Production rotation: see [`docs/runbooks/rotate-jwt-keys.md`](docs/runbooks/rotate-jwt-keys.md).
- **Refresh-token rotation** is server-side — refresh families live in Redis (`refresh:fam:<uuid>` hashes). Tests use db 15 with `FLUSHDB`.
- **Branding** — `APP_NAME` env var (default `FastSaaS`) drives the FastAPI title and email subjects; templates substitute `{{ app_name }}` so a fork only has to change one env var.

## Common make targets

| Target | What it does |
|---|---|
| `make dev` | `docker compose up -d` (Postgres / Redis / Mailhog). |
| `make down` | Stop the stack and wipe volumes. |
| `make migrate` | `alembic upgrade head` as the migrator role. |
| `make test` | Backend pytest + frontend vitest. |
| `make lint` | Backend ruff + frontend biome. |
| `make openapi` | Dump `backend/openapi.json` from the live FastAPI app. |
| `make codegen` | Regenerate `frontend/src/api/generated/` from `openapi.json`. |
| `make gen-jwt-keys` | Mint an RS256 keypair into `infra/dev-secrets/jwt/`. |

## Architectural decisions

ADRs live in `requirements/decisions/`. Foundational set:

- **ADR-005** — async FastAPI + arq workers
- **ADR-006** — primary keys (UUID v7) + cascade
- **ADR-007** — multi-tenant isolation via Postgres RLS
- **ADR-008** — auth flow: 15-min RS256 access JWT + 30-day rotating refresh
- **ADR-009** — Actor-Centric CTI (HUMAN / AGENT / SERVICE)
- **ADR-010** — audit log with `intent_hash` grouping
- **ADR-011** — frontend project layout
- **ADR-012** — phased shadcn/ui adoption
- **ADR-013** — capability-based authorization with role bundles
- **ADR-015** — actor type SERVICE
- **ADR-016** — org-policy mechanism
- **ADR-017** — API keys
- **ADR-018** — JOSE + OAuth library: joserfc + authlib

## License

MIT (TBD — finalised before public announce).
