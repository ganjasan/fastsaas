## Context

The `actors`, `users`, `oauth_identities`, `agents`, `services` tables ship in migration 0001 from bootstrap, with all CHECK constraints and CTI relationships per ADR-009 (and its amendment). What's missing: ORM models, auth flows, JWT issuance, token storage, and FastAPI dependencies.

ADR-008 locked the auth bundle: 15-min RS256 access JWT + 30-day rotating refresh, hybrid storage (refresh in httpOnly cookie, access in memory), per-purpose magic-link TTLs, OAuth Google + Microsoft, mandatory email verification before login. ADR-009 locked CTI; the v1 scope is HUMAN-only, but the parent `actors` table is what every downstream FK points at.

Constraints:
- Backend is async FastAPI on asyncpg per ADR-005.
- Real-DB integration tests, no mocks (memory `feedback_workflow.md`; CLAUDE.md root).
- Public-ready repos do not apply here — `fastsaas` is private.
- DACH ICP: Microsoft OAuth is non-negotiable in v1.

## Goals / Non-Goals

**Goals:**
- All HUMAN auth flows from ADR-008 wired end-to-end through real Postgres + Redis + Mailhog in dev.
- Single `current_actor` FastAPI dependency that every protected route uses.
- Refresh-rotation with reuse-detection and family blacklisting.
- ORM models that make `users JOIN actors` ergonomic without forcing it on every query.
- FE login/register/verify/magic-link/reset flows as TanStack-routed pages.
- Migration 0003 introduces `magic_link_tokens` (the only schema not pre-created in bootstrap).

**Non-Goals:**
- AGENT/SERVICE actor creation or login (MCP epic).
- API-key auth (`api_keys` table — separate sub-issue against ADR-017).
- Org membership, project roles, capability checks (#4).
- Audit-log writes from auth events (#5 will hook in via middleware).
- 2FA, passkeys, WebAuthn.
- Production SMTP — Mailhog only in v1.
- Sentry user context — #7.

## Decisions

### D1. JWT signing — RS256 with rotatable keypair

ADR-008 left RS256 vs EdDSA open. We pick **RS256**:

- `joserfc` ships RS256 out of the box (per ADR-018, `joserfc` replaces the deprecated `python-jose`); EdDSA support requires a different key class.
- Key rotation: keep an active `kid` in env (`JWT_SIGNING_KID`) and a list of `kid → public_key` mappings in `JWT_PUBLIC_KEYS_JSON` for verification of in-flight tokens after rotation.
- Initial keypair generated via `make gen-jwt-keys` writing PEM to `secrets/jwt/` (gitignored); dev seed-keys committed under `infra/dev-secrets/jwt/` with a loud `DEV ONLY` README.
- Performance gap (RS256 vs EdDSA) is irrelevant at v1 scale (≤ 10k QPS not in sight).

**Alternative — EdDSA:** smaller / faster, but adds dependency surface and pulls us off the well-trodden path.

### D2. Refresh-token family tracking — Redis hash per family

Each login issues a `family_id` (UUID v7). Each refresh stores in Redis:

```
HSET refresh:fam:<family_id>
  current_jti       <jti>
  user_actor_id     <uuid>
  expires_at        <iso8601>
```

On refresh:
1. Read `current_jti` for the presented family.
2. If presented `jti` ≠ `current_jti` → **reuse detected** → `DEL refresh:fam:<family_id>`, force re-login.
3. Else: rotate — write new `jti`, return new refresh + new access.

On logout: `DEL refresh:fam:<family_id>`.

TTL on the hash matches refresh lifetime (30 days), refreshed on each rotation.

**Alternative — JWT-only refresh, no server state:** simpler, but reuse detection is impossible. Rejected — ADR-008 explicitly requires reuse detection.

### D3. Magic-link tokens — single shared table, `purpose` discriminator

One table with `purpose IN ('email_verification' | 'magic_link_login' | 'password_reset' | 'org_invitation')`. Per-purpose TTL hardcoded in app per ADR-008 §8c (not stored in row); the row carries `expires_at` derived from purpose at insert time.

```sql
CREATE TABLE magic_link_tokens (
  token_hash    TEXT PRIMARY KEY,                    -- sha256(token)
  purpose       TEXT NOT NULL,
  actor_id      UUID NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
  email         CITEXT NOT NULL,                     -- denormalised; supports email-change verification before flipping
  expires_at    TIMESTAMPTZ NOT NULL,
  consumed_at   TIMESTAMPTZ NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT purpose_valid CHECK (purpose IN ('email_verification','magic_link_login','password_reset','org_invitation'))
);
CREATE INDEX magic_link_tokens_actor_purpose_idx ON magic_link_tokens(actor_id, purpose) WHERE consumed_at IS NULL;
```

Single-use enforced via `consumed_at` set in the same transaction as the side effect (e.g. `email_verified := TRUE`).

**Alternative — one table per purpose:** more types, more migrations, no benefit at this scale.

### D4. OAuth — Authlib `AsyncOAuth2Client` with OIDC discovery

Per ADR-018: `authlib.integrations.httpx_client.AsyncOAuth2Client` for both providers; `joserfc` for `id_token` verification. Authlib gives us OIDC discovery, PKCE, JWKS rotation/caching, and `id_token` claim validation (sig/iss/aud/exp/nonce) out of the box — meeting RFC 9700 / OWASP guidance with substantially less hand-rolled code than the prior `httpx-oauth` plan. Both Google and Microsoft are wrapped behind a small `OAuthProvider` protocol so adding GitHub later is one new module.

- State token: signed JWT (5-min TTL) carrying `nonce` + intended `redirect_to` path; verified on callback.
- Microsoft uses the `common` tenant endpoint; `provider_uid = <tid>:<oid>` from the id_token.
- Google: `provider_uid = sub` from the id_token.
- On callback, look up `oauth_identities(provider, provider_uid)`:
  - **Found** → log in the linked user.
  - **Not found** + email matches a `users` row → return 409 with "an account exists; sign in with password and link OAuth".
  - **Not found** + no email match → create `actors`+`users`+`oauth_identities` rows in one transaction; treat email as verified (OAuth provider attests).

**Alternative — `httpx-oauth` + custom OIDC code:** simpler dep but ~300-400 LOC of hand-rolled discovery, JWKS, and id_token validation. Rejected per ADR-018.

### D5. Module layout — `backend/src/fastsaas/identity/`

```
backend/src/fastsaas/identity/
├── __init__.py
├── models.py            # Actor, User, OAuthIdentity, MagicLinkToken (SQLModel)
├── schemas.py           # Pydantic — RegisterRequest, LoginRequest, CurrentActor, ...
├── auth/
│   ├── __init__.py
│   ├── password.py      # Argon2id hashing (passlib[argon2])
│   ├── jwt.py           # encode/decode + key loading
│   ├── refresh.py       # Redis family tracking + rotation
│   ├── magic_link.py    # token mint/consume per purpose
│   └── oauth.py         # provider protocol + Google/Microsoft impls
├── email.py             # Jinja2 templates rendered at module import
├── middleware.py        # current_actor, require_human, require_verified_email
└── service.py           # use-case-level orchestration (register, login, ...)
```

Routes live in `backend/src/fastsaas/api/auth.py` and call `service.py` only — no SQL or JWT calls in handlers.

### D6. Frontend — `frontend/src/features/auth/`

Feature-folder per ADR-011. Routes registered under `/auth/*` in `__root.tsx`:

```
frontend/src/features/auth/
├── routes/              # TanStack file-based routes
│   ├── login.tsx
│   ├── register.tsx
│   ├── verify-email.$token.tsx
│   ├── magic-link.$token.tsx
│   ├── reset-password.$token.tsx
│   └── oauth.$provider.callback.tsx
├── components/          # form components
├── lib/
│   ├── authStore.ts     # Zustand — in-memory access token + actor
│   └── refreshFlow.ts   # 401-retry mutator hooked into orval
└── api/                 # generated calls re-exported
```

Refresh-on-401: orval mutator wraps fetch — on 401, calls `/auth/refresh` once with `X-Refresh: 1`, retries the original request with the new access token. Concurrent 401s share a single in-flight refresh promise (per ADR-008 negative consequence).

### D7. Email — Jinja2 templates, sync rendering, async send

Templates live in `backend/src/fastsaas/identity/templates/` (`*.html.j2` + `*.txt.j2`). Render synchronously (templates are tiny), send via `aiosmtplib` to Mailhog (`localhost:1025` in dev).

Subject lines + URL templates configurable via `Settings.identity_*`. Production SMTP is the same code path — only host/port/credentials differ.

### D8. Argon2id parameters

`passlib[argon2]` with parameters tuned per OWASP password-storage cheatsheet:

```python
PASSWORD_CTX = CryptContext(
    schemes=["argon2"],
    argon2__memory_cost=64 * 1024,  # 64 MiB
    argon2__time_cost=3,
    argon2__parallelism=4,
)
```

Verifies `< 500ms` on dev hardware; revisit only if profiling complains.

## Risks / Trade-offs

- **OAuth in CI E2E** → CI cannot do real Google/Microsoft round-trips. **Mitigation:** an `OAUTH_DEV_BYPASS=true` env var enables a fake provider (`/auth/oauth/dev/start` immediately calls the callback with a configured email). Off in prod, on in CI + local dev when wanted.
- **Refresh-rotation race** → two concurrent refreshes could both win without care. **Mitigation:** Redis `WATCH/MULTI/EXEC` (or simpler: `INCR` on a per-family counter and require monotonic `jti` index). Documented in `auth/refresh.py`.
- **Microsoft OAuth complexity** → tenant-id handling, common vs consumer endpoints. **Mitigation:** start with `common` endpoint; surface `tenant_id` from the ID token into `oauth_identities.provider_uid` as `<tenant>:<oid>`.
- **Magic-link tokens leak in email** → user forwards an email with a verification link. **Mitigation:** TTLs are short (15 min for login, 1 h for reset); single-use enforces the rest. Acceptable for v1; document in security notes.
- **In-memory access token loss on tab close** → user has to wait for refresh round-trip on next page load. **Mitigation:** automatic on app boot; UX shows skeleton, not login. Acceptable per ADR-008 §8b.

## Migration Plan

- **Migration 0003** — `magic_link_tokens` table only. No data migration; bootstrap shipped without any auth-using rows.
- **Backward compat** — backend additive: new endpoints + new dependency; no existing callers.
- **Rollout** — one PR; deployable independently; no flag gates needed since FE features ship in the same change.
- **Rollback** — revert PR; drop migration 0003 (no FK references from elsewhere yet).

## Open Questions

- **Email-change flow scope.** Out of scope for v1 explicitly — but the proposal mentions "email change" in scope. **Resolution:** include an `update_email` API that emits `email_verification` magic-link to the new address; only flips `users.email` on consumption. Cheap to add and prevents a follow-up sub-issue.
- **Display name on register.** Mandatory or derived from email? **Default:** derive from local-part of email if not provided; user edits in profile (out of scope here, but the field is non-null in `actors`).
- **Rate-limiting** of `POST /auth/login` and magic-link request. **Defer:** add via a thin middleware in #5 Audit (which already needs request-scoped state). Document the gap in tasks as known.
- **JWT key rotation runbook.** Stub a `docs/runbooks/rotate-jwt-keys.md` in this change? **Default:** yes, one-page note; cheap insurance.
