---
title: Identity layer — Actor model + Auth flows + JWT context middleware
status: in_progress
linked_issue: ganjasan/fastsaas#2
created: 2026-05-01
traces_to:
  adr:
    - "[[ADR-008_auth-flow]]"
    - "[[ADR-009_actor-model-cti]]"
  spike: platform-saas-core-architecture-spike
---

## Why

`fastsaas` has the schema for actors / users / oauth_identities (migration 0001 from bootstrap), but no ORM models, no auth flows, no JWT issuance, and no `current_actor` dependency. Until this layer is in place, every subsequent sub-issue (Tenants #3, Audit #4, UI #5, E2E #7) is blocked because they all need to know *who is calling*.

This change implements the v1 SaaS-core identity per ADR-008 (auth flow) and ADR-009 (actor CTI). Scope is HUMAN actors only — AGENT/SERVICE registration ships with the future MCP epic, even though their schemas already exist.

## What Changes

**NEW** Backend ORM models — `backend/src/fastsaas/identity/models.py`:
- `Actor`, `User`, `OAuthIdentity` SQLModel classes mirroring the migration-0001 schema.
- Soft-delete via `deleted_at` per ADR-006.

**NEW** Auth flows — `backend/src/fastsaas/identity/auth/`:
- Register (email + password) — issues an email-verification magic-link via Mailhog.
- Email verification (consumes single-use 24-h token; flips `users.email_verified`).
- Login (email + password) — requires `email_verified = TRUE`; rejects otherwise per ADR-008 §8e.
- Magic-link login (single-use 15-min token).
- Password reset (single-use 1-h token).
- OAuth: Google + Microsoft per ADR-008 §8d (M365 critical for DACH).
- Logout (blacklists refresh family in Redis).

**NEW** JWT — `backend/src/fastsaas/identity/jwt.py`:
- 15-min access token + 30-day rotating refresh per ADR-008 §8a.
- Refresh-reuse detection — replay invalidates the entire family in Redis.
- Access-token claims: `actor_id`, `actor_type`, `parent_actor_id` (null for HUMAN v1).
- Algorithm: RS256 (decision per ADR-008 open question — separate keypair, easy rotation).

**NEW** Token storage — backend response handling:
- Refresh: `Set-Cookie` httpOnly, Secure, SameSite=Lax, Path=/auth.
- Access: returned in JSON body; SPA holds in memory.
- Refresh endpoint requires `X-Refresh: 1` custom header per ADR-008 §8b CSRF.

**NEW** FastAPI middleware — `backend/src/fastsaas/identity/middleware.py`:
- `current_actor` dependency — extracts JWT from `Authorization: Bearer`, validates, loads `Actor`, returns Pydantic `CurrentActor`.
- `require_human` / `require_verified_email` guards as composable dependencies.

**NEW** Magic-link infra — `backend/src/fastsaas/identity/tokens.py`:
- Single-use tokens stored as `sha256(token)`; raw token only in email URL.
- Per-purpose TTLs per ADR-008 §8c.
- Schema NEW: `magic_link_tokens(token_hash, purpose, actor_id, expires_at, used_at)` — migration 0003.

**NEW** Email — `backend/src/fastsaas/identity/email.py`:
- Mailhog SMTP in dev (already in docker-compose).
- Templates for: verification, magic-link login, password reset.
- Production SMTP config deferred — Mailhog interface is identical.

**NEW** Frontend identity — `frontend/src/features/auth/`:
- Routes: `/auth/login`, `/auth/register`, `/auth/verify-email/$token`, `/auth/magic-link/$token`, `/auth/reset-password/$token`, `/auth/oauth/$provider/callback`.
- React Hook Form + Zod for all forms.
- TanStack Query for auth state; Zustand `authStore` for in-memory access token.
- Refresh-on-401 axios/orval mutator that calls `/auth/refresh` and retries once.

**NEW** Backend API surface — `backend/src/fastsaas/api/auth.py`:
- `POST /auth/register`
- `POST /auth/login`
- `POST /auth/logout`
- `POST /auth/refresh`
- `POST /auth/verify-email`
- `POST /auth/magic-link/request`, `POST /auth/magic-link/consume`
- `POST /auth/password-reset/request`, `POST /auth/password-reset/consume`
- `GET /auth/oauth/$provider/start`, `GET /auth/oauth/$provider/callback`
- `GET /auth/me` — returns current `Actor` + `User` view (protected).

**NEW** Tests:
- Backend: pytest GIVEN/WHEN/THEN, integration against real Postgres + Redis + Mailhog (no mocks per memory `feedback_workflow.md`).
- Frontend: Vitest unit on Zustand store + form validation; Playwright E2E for register → verify-via-Mailhog → login.

## Out of scope (deferred)

- AGENT / SERVICE actor lifecycle — MCP epic.
- API-key auth for AGENT/SERVICE — needs `api_keys` table populated; defer to ADR-017 sub-issue.
- Org membership / per-project roles — #4.
- Audit-log middleware integration — #5 (will *consume* `current_actor` from this change).
- Sentry user context — #7.
- Production-grade SMTP — defer to deploy epic.
- 2FA / passkeys — out of v1.
