---
title: Identity layer — tasks
linked_issue: ganjasan/fastsaas#2
---

# Tasks

## 1. Backend deps + scaffolding

- [x] 1.1 Add to `backend/pyproject.toml`: `authlib`, `joserfc`, `passlib[argon2]`, `aiosmtplib`, `jinja2`, `redis` (per ADR-018; `python-jose` and `httpx-oauth` dropped)
- [x] 1.2 Create module skeleton `backend/src/fastsaas/identity/{__init__,models,schemas,middleware,service,email}.py` and `auth/{__init__,password,jwt,refresh,magic_link,oauth}.py`
- [x] 1.3 Extend `backend/src/fastsaas/config.py` with identity settings (JWT keys, OAuth client id/secret, SMTP, magic-link base URL, OAUTH_DEV_BYPASS)
- [x] 1.4 Add Redis async client factory in `backend/src/fastsaas/cache/redis.py` + lifespan wiring in `main.py`

## 2. Migration 0003 — magic_link_tokens

- [x] 2.1 Generate alembic revision for `magic_link_tokens` table per design.md §D3
- [x] 2.2 Add partial index `magic_link_tokens_actor_purpose_idx WHERE consumed_at IS NULL`
- [x] 2.3 Add CHECK `purpose IN ('email_verification','magic_link_login','password_reset','org_invitation')`
- [x] 2.4 Verify migration applies and rolls back cleanly

## 3. ORM models

- [x] 3.1 `Actor` SQLModel — id, actor_type, parent_actor_id, display_name, created_at, deleted_at
- [x] 3.2 `User` SQLModel — actor_id PK/FK, email (CITEXT), password_hash, email_verified, locale, timezone, created_at
- [x] 3.3 `OAuthIdentity` SQLModel — provider, provider_uid composite PK, user_actor_id FK
- [x] 3.4 `MagicLinkToken` SQLModel matching migration 0003

## 4. Password hashing

- [x] 4.1 `auth/password.py` — `hash_password`, `verify_password` using Argon2id with parameters from design.md §D8
- [x] 4.2 `validate_password_policy` enforces min-12-char; `hash_password` calls it before hashing; raises `PasswordTooShortError` with `code = "auth.password_too_short"` (will be wired into `service.register_user` in phase 10)
- [x] 4.3 GIVEN a known password WHEN hashed and verified THEN matches; WHEN tampered hash THEN rejected; plus malformed-hash, threshold, argon2id-marker tests

## 5. JWT issuance + verification

- [x] 5.1 `auth/jwt.py` — load active signing key from `jwt_signing_kid` + `jwt_signing_key_path` (PEM file); load verification keys from `jwt_public_keys_dir` (`<kid>.pub.pem` files); `reload_keys()` for tests + rotation
- [x] 5.2 `encode_access(actor, family_id)` and `decode_access(token)` — RS256, 15-min TTL, claims sub/actor_type/parent_actor_id/family_id/type
- [x] 5.3 `encode_refresh(family_id, jti, user_actor_id)` and `decode_refresh(token)` — RS256, 30-day TTL
- [x] 5.4 Generate dev keypair in `infra/dev-secrets/jwt/dev-1.{pem,pub.pem}` with `DEV ONLY` README; `make gen-jwt-keys` regenerates; defaults in `Settings` resolve to absolute path so cwd doesn't matter
- [x] 5.5 GIVEN/WHEN/THEN tests for access/refresh round-trip, wrong-type rejection, unknown kid, expired exp, rotated kid (old token still verifies, new token uses new kid), and committed dev keypair load

## 6. Refresh-family Redis tracking

- [x] 6.1 `auth/refresh.py` — `start_family(user_actor_id) -> (family_id, jti)`, `rotate(family_id, presented_jti, user_actor_id) -> jti`, `revoke_family(family_id, user_actor_id)`, `revoke_all_for_actor(actor_id)`, `get_current_jti(family_id)`. Uses error classes `RefreshReusedError` (`code=auth.refresh_reused`) / `RefreshUnknownError` (`code=auth.refresh_unknown`).
- [x] 6.2 Atomic rotation via Redis-side Lua script registered through `register_script`; per-actor index `refresh:actor:<actor_id>` (SET) supports `revoke_all_for_actor` in O(N_families).
- [x] 6.3 9 tests cover: state persistence, successful rotation, reuse detection deleting family, unknown family, logout, revoke-all (with/without families), 5-step rotation chain, replay-after-chain blacklists family. Use `redis_client` fixture on DB 15 with FLUSHDB.

## 7. Magic-link tokens

- [x] 7.1 `auth/magic_link.py` — `mint(session, *, actor_id, purpose, email) -> (raw_token, row)`. Raw is `secrets.token_urlsafe(32)`; only `sha256(raw)` reaches the DB. Per-purpose TTL via `PURPOSE_TTL` constant (15min/24h/1h/7d).
- [x] 7.2 `consume(session, *, raw_token, purpose) -> MagicLinkToken | None` — atomic `UPDATE ... WHERE token_hash = sha256(raw) AND purpose = :p AND consumed_at IS NULL AND expires_at > NOW() RETURNING *`. Caller wraps the side effect in the same transaction. `find_active` for read-only lookup.
- [x] 7.3 13 tests: round-trip parameterised on all 4 purposes, hash-only-at-rest, replay rejection, expired rejection, unknown token, wrong purpose, savepoint rollback restores token, find_active is non-consuming, TTL constants match ADR-008 §8c, distinct mints produce distinct tokens.

## 8. OAuth providers (Authlib + joserfc per ADR-018)

- [x] 8.1 `auth/oauth.py` — `OIDCProvider` dataclass; `google_provider()` / `microsoft_provider()` factories built on `AsyncOAuth2Client` with discovery fetched on first use and cached; `id_token` validated via `joserfc` against the provider JWKS (sig + iss + aud + exp + nonce). PKCE S256 challenge wired in. `provider_uid` is `sub` for Google, `<tid>:<oid>` for Microsoft.
- [x] 8.2 State token: 5-min RS256 JWT in `auth/oauth_state.py` carrying `provider`/`nonce`/`redirect_to`; signs with the same active kid as access tokens; `decode_with_type` distinguishes it from access/refresh.
- [x] 8.3 `service.complete_oauth(provider, identity)` — branch logic per auth-flows spec (linked → log in, email-only-match → 409 oauth_email_taken, fresh → create actor+user+identity with email_verified=TRUE).
- [x] 8.4 Dev bypass: `/auth/oauth/dev/start?email=...` returns 404 unless `OAUTH_DEV_BYPASS=true`. Route declared before `/oauth/{provider}/start` so FastAPI doesn't treat "dev" as a provider name.
- [x] 8.5 Provider unit tests (10): authorize-URL has client_id/state/code_challenge/nonce; happy-path returns claims; rejects state for other provider, wrong-nonce id_token, wrong-aud, wrong-iss, expired, signature-by-wrong-key. End-to-end Google flow with respx will land alongside the bypass route in Phase 10.

## 9. Email rendering + delivery

- [x] 9.1 Jinja2 templates in `identity/templates/` — `verification`, `magic_link_login`, `password_reset` (each as `.html.j2` + `.txt.j2`). Custom autoescape predicate escapes HTML only; plain-text bodies are passthrough.
- [x] 9.2 `email.py` — `render(template, **ctx)` + `send(...)` + three high-level helpers `send_verification`, `send_magic_link`, `send_password_reset`. Multipart alternative (text + html). Delivery via `aiosmtplib` to `SMTP_HOST:SMTP_PORT`.
- [x] 9.3 Tests against running Mailhog (skip if unreachable): renders escape HTML in html-only; verification/magic-link/password-reset arrive with the right subject, recipient, URL token; multipart/alternative carried through.

## 10. FastAPI middleware + routes

- [x] 10.1 `middleware.py` — `current_actor` (Authorization: Bearer parsing + actor load + soft-delete check), `require_human`, `require_verified_email`. Errors are HTTPException with `{code, message}`.
- [x] 10.2 `api/auth.py` — register, login, logout, refresh, verify-email, magic-link request/consume, password-reset request/consume, oauth start/callback per provider, `/auth/me`, `/auth/oauth/dev/start`. Email side effects piggy-back on FastAPI BackgroundTasks (run AFTER session commit).
- [x] 10.3 `APIRouter(prefix="/auth")` mounted in `main.py` via `app.include_router(auth_router)`.
- [x] 10.4 `/auth/refresh` requires `X-Refresh: 1`; missing → 400 `auth.refresh_missing_header`.
- [x] 10.5 Refresh cookie: HttpOnly, Secure (off in dev), SameSite=Lax, Path=/auth, Max-Age=2592000. PKCE cookie analogous, Path=/auth, Max-Age=600.

## 11. Backend integration tests (real Postgres + Redis + Mailhog)

- [x] 11.1 `conftest.py` extension: `redis_client` (db 15 + flush), `mailhog` (skip if unreachable + flush), `clean_identity` (delete actors as migrator pre + post test), `client` (resets `fastsaas.db` engine to defeat closed-loop pool).
- [x] 11.2 `tests/test_api_auth.py` (19 tests) covers auth-flows scenarios: register success/dup/short-pw, login verified/unverified/wrong-pw/unknown, /me variants, refresh+rotation+reuse, logout, magic-link, password-reset wipes refreshes, OAuth dev-bypass enabled/disabled.
- [x] 11.3 Session-tokens scenarios covered alongside (refresh requires X-Refresh, cookie attrs verified, reuse blacklists family, logout invalidates).
- [x] 11.4 Actor-identity dependency scenarios covered (token missing → 401, garbage token → 401, valid bearer → CurrentActor; CTI inserts already verified at unit level in test_identity_models).
- [x] 11.5 CI green on PR #11 (run 25228389120) — Backend + Frontend + OpenAPI codegen drift + E2E (Playwright) all pass. Required adding `redis:7-alpine` and `mailhog/mailhog:latest` service containers to both `backend` and `e2e` jobs.

## 12. Frontend feature module

- [x] 12.1 Existing deps already cover: `@hookform/resolvers ^5`, `react-hook-form ^7`, `zod ^3`, `zustand ^5`. `@faker-js/faker` added as devDep so orval's MSW mocks compile.
- [x] 12.2 `frontend/src/features/auth/{lib,components}/` per design.md §D6.
- [x] 12.3 File-based routes: `/auth/login`, `/auth/register`, `/auth/verify-email/$token`, `/auth/magic-link/$token`, `/auth/reset-password/$token`. `/auth/oauth/$provider/callback` deferred — bypass route is the working OAuth flow in v1; real-provider FE callback lands with Phase 14.4.
- [x] 12.4 `authStore.ts` (Zustand) — `accessToken`, `currentActor`, `setSession`, `setAccessToken`, `setCurrentActor`, `clear`. Imperative `tokenStore` shim for the orval mutator.
- [x] 12.5 `refreshFlow.ts` — single in-flight refresh promise (concurrent 401s share); refresh failure clears the store + redirects to `/auth/login`. Wired from `lib/api/client.ts` so every orval call benefits.
- [x] 12.6 Login + register + reset-password forms use react-hook-form + zod (`schemas.ts`); password policy mirrors backend min-12 from ADR-008 §8c. Backend error codes (`auth.email_taken`, `auth.email_unverified`, `auth.invalid_credentials`, `auth.password_too_short`, `auth.token_invalid|expired`) are mapped to user-facing copy.

## 13. Codegen + OpenAPI sync

- [ ] 13.1 Run `make openapi` to refresh `backend/openapi.json`
- [ ] 13.2 Run `npm run codegen` (orval) to regenerate `frontend/src/api/generated/`
- [ ] 13.3 Codegen-drift CI job stays green

## 14. Frontend tests

- [x] 14.1 Vitest unit (`authStore.test.ts`, `authSchemas.test.ts`): setSession/clear/setAccessToken reducers; zod login/register/reset schemas accept valid input + reject malformed email + reject < 12-char passwords with the policy message.
- [x] 14.2 Vitest unit (`refreshFlow.test.ts`): single-in-flight invariant (3 concurrent callers ⇒ 1 fetch), serial calls dispatch new fetches, recoverFrom401 success-path writes the token + returns it, failure-path clears the store + redirects to `/auth/login`, failure while already on `/auth/login` does NOT redirect (no loop).
- [ ] 14.3 Playwright E2E: register → fetch verification email from Mailhog API → click link → login → hit `/auth/me` — deferred to a follow-up; the unit + integration coverage already exercises every link in the chain.
- [ ] 14.4 Playwright E2E: OAuth dev-bypass flow — deferred alongside 14.3.

## 15. Operational hygiene

- [x] 15.1 `docs/runbooks/rotate-jwt-keys.md` — one-page runbook covering when, the dual-publish window, rollback before the cutover, and the unit tests that exercise the rotated-kid path.
- [x] 15.2 `.env.example` extended with SMTP_*, APP_URL, JWT_SIGNING_KID, JWT_SIGNING_KEY_PATH, JWT_PUBLIC_KEYS_DIR, OAUTH_GOOGLE_*, OAUTH_MICROSOFT_*, OAUTH_DEV_BYPASS — defaults still resolve to in-repo dev secrets so a clean clone runs.
- [x] 15.3 New `README.md` — quick start, repo layout, "Auth in dev" pointing at Mailhog UI, dev bypass, dev keypair, refresh-rotation Redis scheme.

## 16. Verify + ship

- [x] 16.1 `make test` green locally — 83 backend (Postgres + Redis + Mailhog) + 17 frontend Vitest = 100. Lint clean (ruff + biome).
- [x] 16.2 README quick-start documents the path: `cp .env.example .env && make dev && make migrate && make -C backend dev && make -C frontend dev`. Dev keypair already in repo, so a clean clone reaches `/auth/me` without manual secret setup.
- [x] 16.3 CI green on PR #11 (run 25228389120) — all 4 jobs pass.
- [ ] 16.4 PR #11 open; archive change before merge.

## Out of scope (defer)

- AGENT/SERVICE actor login → MCP epic
- API-key auth (`api_keys`) → separate sub-issue
- Org membership / project roles → #4
- Audit-log writes from auth events → #5 (consumes `current_actor` from this change)
- Rate-limiting on `/auth/*` → #5 (request-scoped middleware)
- 2FA / passkeys / WebAuthn → out of v1
- Production SMTP credentials → deploy epic
- Sentry user context → #7
