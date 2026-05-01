---
title: Platform SaaS core — design.md (spike)
status: draft
linked_issue: the SaaS-core architecture spike
created: 2026-05-01
---

# Platform SaaS core — overall architecture design

This document is the living working notes for the spike. As each decision is resolved, the corresponding section is filled and an ADR is created in `fastsaas/requirements/decisions/`. Once all 10 decisions land, this file becomes the consolidated map (which ADR covers what; how the layers fit together).

> **Status legend:** 🟦 open · 🟨 in discussion · 🟩 decided (link to ADR) · 🟥 deferred (rationale).

---

## Context

Target repo: `platform/`. Current state: empty `backend/src/fastsaas/{registry,execution,data,tenants,audit,cache,api}/.gitkeep`, empty `frontend/src/{renderer,stores,views}/`. No code committed.

Stack already locked:
- **ADR-002** — Three independent components (Model · Protocol · Orchestrator).
- **ADR-004** — Frontend stack (React 18 + Vite 5 + TanStack + Radix + Tailwind).

Out of scope for this spike: FASTSAAS-specific runtime (Model Registry, Execution Engine, FASTSAAS 5-level hierarchy). Those land in epic #2.

---

## Decision matrix

### 1. Async strategy 🟩
**Question:** sync FastAPI handlers vs async; what runs long-running work?

**Decision:** **(B) Async FastAPI throughout + arq workers** (Redis-backed async worker).
- DB driver: **asyncpg** (async-native).
- Tests: `pytest-asyncio` across the suite as standard convention.
- Workers run in a separate process from web servers (same image, different command).

**Rationale:**
- Forcing function: epic #2 (Orchestrator core) requires streaming model-execution progress to the user (SSE / WebSocket). Native async streaming via `StreamingResponse` is cheap; bolting it onto a sync app means a separate WebSocket sidecar.
- arq shares the asyncio event loop and asyncpg connection pool, so workers and web are operationally homogeneous.
- Python 3.12 async tooling (TaskGroup, modern `asyncio`) is mature; the historical async-pain is no longer a real cost.

**Trade-off accepted:** every test is async; mixed `def`/`async def` route handlers are forbidden (footgun). One sync escape hatch — `run_in_threadpool` — only for proven CPU-bound code.

**Output:** ADR to be created (likely **ADR-005 — Async-throughout FastAPI + arq for SaaS-core**). Logged in tasks.md.

**Open sub-questions for later:** when to use `arq.create_task` vs inline `asyncio.create_task` (rule of thumb: > 500 ms or external IO retry → arq); user-initiated cancellation (deferred to epic #2 streaming work).

---

### 2. Hierarchy primary keys 🟩
**Question:** PK type and cascade strategy for `organisations`, `projects`, `actors`, `audit_log`.

**Decision:**
- **PK type:** **UUID v7** (RFC 9562, time-ordered) — generated in Python via `uuid_utils` (or equivalent), stored as Postgres `UUID` column.
- **Cascade strategy — domain (Org / Project / membership / settings):** **soft-delete** with `deleted_at TIMESTAMP NULL`; queries filter `WHERE deleted_at IS NULL`.
- **Cascade strategy — `audit_log` and any compliance-related table:** **never deleted**. FK to `organisations.id` is nullable, no `ON DELETE` clause. Even on hard org-delete (admin tooling, GDPR right-to-erasure of user PII) the audit row survives with the FK becoming an orphan reference, which is acceptable for a log.

**Rationale:**
- UUID v7 vs serial: serial leaks tenant cardinality (`/orgs/47` reveals you have ≤ 47 orgs); v7 doesn't, while still indexing efficiently because the high bits are time-ordered (no B-tree fragmentation that plagues UUID v4).
- UUID v7 in Python (no Postgres extension): works with managed Postgres (RDS, Supabase, Neon) without `pg_uuidv7` install.
- Soft-delete + audit-log-immortality protects compliance: industry-specific compliance / SOC-2-style audits require a contiguous trail. Cascading audit deletion would make compliance impossible.

**Trade-off accepted:**
- Slightly larger storage (16B vs 8B PK, ×N rows) — negligible at SaaS scale.
- Soft-delete must be enforced in queries everywhere — handled by a base SQLModel mixin or RLS policy per decision #3.
- Future FASTSAAS 5-level hierarchy (Portfolio → Asset → Analysis → Scenario) inherits the same scheme for consistency.

**Output:** ADR (likely **ADR-006 — Primary keys & cascade strategy**) — covers both PK type and the audit-immortality rule.

**Open sub-questions:**
- Add an internal `_pk SERIAL` for JOIN performance? *Deferred — only if profiling shows pain.*
- ULID instead of UUID v7 for shorter URLs? *Rejected — UUID v7 is standardized (RFC 9562) and natively typed in Postgres; ULID would need a custom type.*

---

### 3. Multi-tenant isolation 🟩
**Question:** Postgres RLS vs app-level filter — pick one or both.

**Decision:** **(C) Both — RLS in production schema as a hard guarantee + app-level WHERE for ergonomics and explicit intent.**

**Mechanics:**
- Every tenant-scoped table gets `ALTER TABLE … ENABLE ROW LEVEL SECURITY` and a `tenant_isolation` policy:
 ```sql
 USING (organisation_id = current_setting('app.current_org', true)::uuid)
 WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid)
 ```
- A FastAPI dependency wraps each request in a transaction and runs `SET LOCAL app.current_org = '<uuid>'` before any query.
- App code still writes explicit `WHERE organisation_id = current_org` — the RLS catches the case where the WHERE was forgotten; the explicit WHERE keeps intent obvious to readers and helps the planner pick indexes.
- Two Postgres roles:
 - `app_user` — no `BYPASSRLS`. Used by the FastAPI app and arq workers.
 - `alembic_migrator` — `BYPASSRLS`. Used by migrations and `pg_dump`.

**Tables exempt from RLS:**
- `audit_log` — its own policy: writes always allowed; reads filtered by tenant for user views, but admin / compliance views need cross-tenant — via the `BYPASSRLS` role.
- System tables (`alembic_version`, etc.).
- Future global / non-tenant tables (system settings, ontology references) — no RLS.

**Per-org theme persistence (foundation for #10 Phase 1):**
- `organisations` carries a `theme JSONB DEFAULT '{}'` column for brand overrides (primary colour, radius, font, etc.).
- Read on every request to inject the active theme into the SSR-or-CSR response.
- The UI Theme Picker in v1 writes to this column. Phase 2 (separate epic) replaces the picker with a full design-system admin page.

**Rationale:**
- Tenant isolation failure is the single highest-impact bug class in SaaS. Paying ~5–10 % query overhead for a database-enforced guarantee is the right trade.
- AI-assisted code (Claude / Cursor) regularly omits tenant filters; RLS is the last-line defense against that class of bug.
- Compliance story (industry-specific compliance / SOC-2 / GDPR) is materially stronger with "Postgres-enforced isolation" than with "we have tests."

**Trade-offs accepted:**
- Test ergonomics: every test fixture must `SET LOCAL` for the active tenant. Captured in a base `tenant_session` pytest fixture.
- Migrations are written under the `alembic_migrator` role; the role split must be documented and respected.
- `pg_dump` for backup uses `alembic_migrator`.
- Admin / billing reports across tenants require the `BYPASSRLS` role or a per-org loop with `SET LOCAL`.

**Output:** ADR (likely **ADR-007 — Multi-tenant isolation: RLS + app-level WHERE**).

**Open sub-questions:**
- Cross-tenant admin endpoints (billing rollup) — service role vs per-org loop? *Defer to first cross-tenant feature.*
- Connection pool: `app.current_org` is `SET LOCAL` per transaction. Confirm asyncpg pool semantics handle this safely (LOCAL is connection-scoped, transaction lifetime). *Verify in bootstrap (#2 in platform).*

---

### 4. Auth flow details 🟩
**Question:** JWT lifetimes, browser storage, magic-link TTLs, OAuth providers — taken as one bundle.

**Decision:**

**4a. JWT lifetime — short access + rotating refresh.**
- Access token: **15 minutes**, JWT signed (RS256 or EdDSA — pick at impl time).
- Refresh token: **30 days, rotating**. Each use issues a new refresh, invalidates the prior. Reuse-detection: if an old refresh is presented, the entire family (current + descendants) is blacklisted in Redis and the user is forced to re-login.
- Logout: blacklist refresh in Redis with TTL = remaining lifetime. Access tokens expire naturally within 15 min (acceptable window).

**4b. Browser storage — hybrid.**
- **Access token: in-memory** (held in TanStack Query state / React context; lost on tab close — fetched anew via refresh).
- **Refresh token: httpOnly cookie**, `Secure`, `SameSite=Lax`, scoped to `/auth/*` path.
- No tokens in `localStorage` or `sessionStorage` — XSS cannot exfiltrate either token.
- CSRF: SameSite=Lax covers cross-site POST; for safety the refresh endpoint additionally requires a custom header (`X-Refresh: 1`) which a cross-site form cannot set.

**4c. Magic-link TTLs — per purpose, single-use.**
| Purpose | TTL | Reuse |
|---------|-----|-------|
| Login magic-link | 15 min | single-use |
| Email verification | 24 h | single-use |
| Org invitation | 7 days | single-use |
| Password reset | 1 h | single-use |

All tokens stored as `sha256(token)` in DB; raw token only in the email URL.

**4d. OAuth providers in v1 — Google + Microsoft (M365).**
- **Google:** broad coverage, all audiences.
- **Microsoft (M365):** critical for target market corporate clients (Acme Consulting, Globex).
- **Deferred from v1:** GitHub (re-evaluate when / if FASTSAAS goes public-ready), Apple (B2B-web SaaS, not needed), LinkedIn.

**Email verification before login: required.** No verified email → no login (and no magic-link issued).

**Out of v1 SaaS-core (own epic later):** MFA / 2FA, SSO / SAML / SCIM — enterprise-tier hardening.

**Rationale:**
- Hybrid storage is the OWASP-recommended pattern for SPAs and gives both XSS resistance (access in-memory) and JS-invisible refresh (httpOnly cookie).
- 15-minute access window keeps blast radius small if a token leaks via, e.g., a bug in third-party JS.
- Refresh rotation + reuse detection turns a stolen refresh into a forced logout (defender wins).
- Microsoft OAuth selection is driven by the target market corporate ICP, not generic enthusiasm — confirmed acceptable trade vs. dropping GitHub.

**Output:** ADR (likely **ADR-008 — Auth flow: hybrid token storage, rotating refresh, OAuth providers**).

**Open sub-questions deferred to bootstrap (#2 in platform):**
- Library choice — `fastapi-users`, `authlib`, or hand-rolled with `python-jose` + `httpx-oauth`. Lean toward **hand-rolled minimal** to keep the surface understood.
- JWT signing algo: RS256 (separate keypair, easy to rotate) vs EdDSA (smaller, faster).
- Redis key schema for blacklisted refresh families.

---

### 5. Actor vs User 🟩
**Question:** how to model HUMAN and AGENT actors in the schema.

**Decision:** **(C) Class Table Inheritance — `actors` parent table + `users` and `agents` child tables, FK 1:1 from child to parent.**

**Schema sketch:**

```sql
CREATE TABLE actors (
 id UUID PRIMARY KEY, -- UUID v7
 actor_type TEXT NOT NULL, -- 'HUMAN' | 'AGENT'
 parent_actor_id UUID NULL REFERENCES actors(id), -- AGENT.parent → HUMAN
 display_name TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 deleted_at TIMESTAMPTZ NULL, -- soft-delete per decision #2
 CONSTRAINT actor_type_valid CHECK (actor_type IN ('HUMAN','AGENT')),
 CONSTRAINT agent_has_parent CHECK (actor_type <> 'AGENT' OR parent_actor_id IS NOT NULL),
 CONSTRAINT human_no_parent CHECK (actor_type <> 'HUMAN' OR parent_actor_id IS NULL)
);

CREATE TABLE users (
 actor_id UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
 email CITEXT UNIQUE NOT NULL,
 password_hash TEXT NULL, -- NULL for OAuth-only users
 email_verified BOOLEAN NOT NULL DEFAULT FALSE,
 locale TEXT NOT NULL DEFAULT 'en',
 timezone TEXT NOT NULL DEFAULT 'UTC',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE oauth_identities (
 user_actor_id UUID NOT NULL REFERENCES users(actor_id) ON DELETE CASCADE,
 provider TEXT NOT NULL, -- 'google' | 'microsoft'
 provider_uid TEXT NOT NULL,
 PRIMARY KEY (provider, provider_uid)
);

CREATE TABLE agents (
 actor_id UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
 api_key_hash TEXT NOT NULL,
 allowed_scopes TEXT[] NOT NULL DEFAULT '{}',
 created_via TEXT NOT NULL, -- 'claude' | 'cursor' | 'mcp' |...
 last_used_at TIMESTAMPTZ NULL
);

CREATE TABLE audit_log (
 id UUID PRIMARY KEY,
 actor_id UUID NOT NULL REFERENCES actors(id), -- FK integrity guaranteed
 actor_type TEXT NOT NULL, -- denormalised for filter without JOIN
 parent_actor_id UUID NULL, -- denorm: AGENT initiator...
);
```

**Rationale:**
- **FK integrity for `audit_log.actor_id`** is preserved — every audit row references a real actor row regardless of type. Compliance leverage.
- **Clean child schemas** — `users` has `email NOT NULL`, `agents` has `api_key_hash NOT NULL`, no nullable bloat in a shared table.
- **Extensibility** — adding a future `actor_type` (e.g. `MODEL` for FASTSAAS model containers in epic #2, or `SERVICE` for machine-to-machine) is just a new child table + extending the `CHECK` constraint.
- **CASCADE** from `actors` to `users`/`agents` keeps the 1:1 invariant: deleting an `actors` row removes the child automatically.

**v1 scope reminder:** the schema for `agents` and `oauth_identities` ships in bootstrap (#2 in platform), but **AGENT-actor creation/management endpoints are NOT in v1 SaaS-core** — they land with the future MCP epic. Only HUMAN registration is wired up.

**Trade-offs accepted:**
- Two INSERTs to create a user (`actors` + `users`) — wrapped in a transaction; trivial cost.
- Common queries that need user fields require JOIN (`SELECT … FROM actors a JOIN users u ON u.actor_id = a.id`). For listing humans we instead query `users` directly + JOIN to `actors` only when type-agnostic data (display_name) is needed.
- Pydantic / SQLModel needs a `UserResponse` view that joins both — handled by the API layer.

**Output:** ADR (likely **ADR-009 — Actor model: CTI with users/agents children**).

**Open sub-questions deferred:**
- AGENT cascade behaviour when parent HUMAN is soft-deleted: cascade soft-delete the AGENT, or keep it usable? *Defer to MCP epic.*
- API-key rotation policy for agents. *Defer to MCP epic.*

---

### 6. `intent_hash` algorithm 🟩
**Question:** how to compute `intent_hash` and whether to act on it for idempotency.

**Decision:** **(D) Hybrid with prefixed source — fall through four sources in priority order, write to `audit_log` but defer idempotency-cache action to a later epic.**

**Algorithm:**

```python
def compute_intent_hash(request: Request, actor: Actor) -> str:
 # 1. Explicit client Idempotency-Key (Stripe-style)
 if (key := request.headers.get("Idempotency-Key")):
 return f"idem:{key}"

 # 2. AGENT-initiated, original-prompt hash (provenance)
 if (prompt := request.headers.get("X-Agent-Intent")):
 canonical = f"{actor.id}:{prompt}"
 return f"agent:{sha256(canonical.encode()).hexdigest()[:16]}"

 # 3. Multi-step UI flow — session-scoped intent (set by frontend on flow start)
 if (sess := request.state.session_intent):
 return f"sess:{sess}"

 # 4. Default — unique per request
 return f"req:{uuid.uuid4().hex}"
```

The prefix (`idem:`, `agent:`, `sess:`, `req:`) is part of the stored value — readable in `audit_log` and lets queries filter by mechanism (e.g. "show me everything an AGENT did this week").

**v1 SaaS-core scope:**
- Compute and persist `intent_hash` for every audit entry — yes.
- Idempotency-cache (look up `intent_hash` in Redis, return cached response on collision) — **deferred to a later epic** (likely MCP / agent-retry epic). For now, repeated `Idempotency-Key` simply produces multiple audit entries that share the hash; the application may detect and reject duplicates only at obvious uniqueness constraints (e.g. unique email).

**`X-Agent-Intent` payload:**
- `intent_hash` stores only the truncated SHA-256.
- The raw prompt is **also** stored in `audit_log.intent_metadata` JSONB (key `original_prompt`) so an audit reviewer can see what the user asked the agent to do. AGENT-callers must respect this when crafting the prompt — no secrets pasted into prompts.

**Hash length:** SHA-256 truncated to 16 hex chars (8 bytes). Collision probability negligible at our scale; keeps the column compact and the value glanceable.

**Rationale:**
- A single mechanism cannot serve all three needs: idempotent retry (HTTP), agent provenance (LLM call), grouped multi-step UI flow (frontend wizard). The hybrid covers each with the smallest possible surface.
- Deferring the idempotency cache lets us ship #16 without solving response-replay semantics (status codes, headers, body equivalence) which is its own design problem.
- AGENT-provenance from day 1 is a near-zero-cost addition — it just means the middleware respects an extra header. Pays off the moment the MCP epic ships.

**Output:** Captured in `design.md`; small enough not to need its own ADR (per `tasks.md`).

**Open sub-questions deferred:**
- Idempotency-cache shape (Redis schema, response replay) — own epic.
- Privacy review of writing raw `original_prompt` to audit — revisit with first AGENT integration; may need redaction policy.

---

### 7. Audit log shape 🟩
**Question:** how to model audit data — table with diff vs event sourcing; retention; partitioning.

**Decision:** **(A) Classic `audit_log` table with JSONB `{before, after}` diff. Event sourcing rejected for v1.**

**Schema:**

```sql
CREATE TABLE audit_log (
 id UUID PRIMARY KEY, -- UUID v7
 timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 actor_id UUID NOT NULL REFERENCES actors(id), -- FK integrity per #5
 actor_type TEXT NOT NULL, -- denormalised
 parent_actor_id UUID NULL, -- denorm: AGENT initiator
 organisation_id UUID NULL, -- nullable: org-deleted survives (per #2 immortality)
 intent_hash TEXT NOT NULL, -- per #6
 entity_type TEXT NOT NULL, -- 'project' | 'user' | 'organisation' | …
 entity_id UUID NOT NULL,
 action TEXT NOT NULL CHECK (action IN ('create','update','delete','restore')),
 diff JSONB NOT NULL, -- {"before": {...}, "after": {...}} — only changed fields
 intent_metadata JSONB NOT NULL DEFAULT '{}' -- {request_id, ip, user_agent, original_prompt,...}
);

CREATE INDEX idx_audit_org_entity_time ON audit_log (organisation_id, entity_type, entity_id, timestamp DESC);
CREATE INDEX idx_audit_intent_hash ON audit_log (intent_hash);
CREATE INDEX idx_audit_actor_time ON audit_log (actor_id, timestamp DESC);
CREATE INDEX idx_audit_timestamp ON audit_log (timestamp DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_tenant_read ON audit_log
 FOR SELECT
 USING (organisation_id = current_setting('app.current_org', true)::uuid);
CREATE POLICY audit_write ON audit_log
 FOR INSERT WITH CHECK (true);
-- No UPDATE / DELETE policies → app role cannot mutate audit rows (immortal per #2)
```

**Diff format: `{before, after}` of changed fields only.**

```jsonc
// create
{ "before": {}, "after": {"name": "Q4 Valuation", "owner_id": "..."} }
// update
{ "before": {"name": "Q4 Valuation"}, "after": {"name": "Q4 Valuation 2026"} }
// delete
{ "before": {"name": "Q4 Valuation 2026", /* full state */}, "after": {} }
```

Compact (only modified fields), explicit (both sides present), replay-friendly.

**Sensitive-field redaction:** middleware maintains a list of fields never written to `audit_log.diff` (`password_hash`, `api_key_hash`, OAuth secrets, etc.). Listed once in code; PRs that add new sensitive fields must extend the list (CI lint TBD).

**Partitioning: deferred.** v1 ships an unpartitioned table. Add `PARTITION BY RANGE (timestamp)` (monthly) when row-count crosses ~10 M. Tracked as a backlog item.

**Retention: immortal by default (per #2).**
- GDPR right-to-erasure handled separately: a future endpoint anonymises PII fields inside `intent_metadata` (IP, user-agent, `original_prompt`) while keeping `actor_id`, `entity_type`, `entity_id`, `action`, `intent_hash`. The structural audit trail is preserved; user-identifying content is scrubbed. Backlog item for post-v1.
- industry-specific compliance / SOC-2 retention satisfied by "kept indefinitely."

**Rationale:**
- Classic `audit_log` covers all four target use cases (compliance, debugging, AI-agent provenance, user activity feed) with the lowest implementation cost.
- Event sourcing solves a different problem (state reconstruction from event stream) that we don't have. Adopting it would force projection-design decisions for every entity, which is a spike of its own. We keep that door open: a future event-sourced subdomain can coexist alongside `audit_log`.
- `{before, after}` over `{changed: {field: [old, new]}}` because the duplication is small and the read-side cost (UI diff renderer, debug REPL) is materially lower.

**Output:** ADR (likely **ADR-010 — Audit log shape: table with JSONB diff**).

**Open sub-questions deferred:**
- Field-redaction list — write down in bootstrap (#2 in platform); CI lint a future tightening.
- Partitioning trigger threshold + ops runbook — when row count nears 10 M.
- GDPR erasure endpoint + UX — own backlog item.

---

### 8. OpenAPI codegen tool 🟩
**Question:** how the React frontend gets typed API access from FastAPI's OpenAPI schema.

**Decision:** **(B) `orval` with the TanStack Query (`react-query`) client + MSW mocks.**

**Pipeline:**

```
backend (FastAPI) ──► /openapi.json (auto)
 │
 ▼
 orval (CI + local pre-PR)
 │
 ▼
 src/api/generated/ — typed hooks per tag
 │
 ▼
 frontend (React + TanStack Query)
 → typed useGetProject, useUpdateProject, …
```

**Sketch config:**

```ts
// frontend/orval.config.ts
export default {
 fastsaas: {
 input: 'http://localhost:8000/openapi.json',
 output: {
 target: 'src/api/generated/',
 client: 'react-query', // TanStack Query bindings
 mode: 'tags-split', // file per OpenAPI tag
 mock: { type: 'msw' }, // MSW handlers for tests
 override: {
 mutator: {
 path: 'src/lib/api/client.ts', // custom fetch wrapper
 name: 'apiClient', // adds JWT (in-memory access token, per #4)
 },
 },
 },
 },
};
```

**CI integration:**
- `make openapi` → backend dumps `openapi.json` to a known path.
- `npm run codegen` → orval generates `frontend/src/api/generated/`.
- `git diff --exit-code frontend/src/api/generated/` fails the build if a backend change wasn't propagated. Catches drift before merge.

**Generated files:** committed to git; `.gitattributes` marks them `linguist-generated=true` so they don't bloat PR reviews but remain visible.

**Custom mutator (`src/lib/api/client.ts`):**
- Reads access token from in-memory store (per #4 hybrid storage).
- Refreshes via httpOnly-cookie refresh endpoint on 401, retries the original request once, redirects to `/login` on definitive failure.
- Sets `Idempotency-Key` header for mutation hooks where the call site opts in (per #6).

**Rationale:**
- We are already committed to TanStack Query (ADR-004); orval generates hooks bound to it directly, eliminating manual wrappers.
- MSW mock generation lets E2E (#7 in platform) and component tests run frontend-only against contract-faithful mocks during fast iterations.
- orval is mature (~12 K stars, 2021+); kubb is the more modern option but hasn't yet earned the production hours.

**Trade-offs accepted:**
- Generated code is verbose; treat `frontend/src/api/generated/` as black-box, never edit by hand.
- Extra build step; mitigated by CI-enforced regen + drift check.

**Output:** Captured in `design.md`; not large enough to warrant a dedicated ADR (per `tasks.md`). Mention in `platform/CLAUDE.md` so agent context knows the convention.

**Open sub-questions:**
- OpenAPI 3.0 vs 3.1 — confirm FastAPI version's default in bootstrap; orval supports both.
- Pre-commit hook for codegen — nice-to-have; CI drift check is the contract.

---

### 9. Frontend project layout 🟩
**Question:** folder structure for `frontend/src/` and which library (if any) handles UI state outside TanStack Query and TanStack Router.

**Decision:**
- **Folder structure: hybrid — `features/<domain>/` + `components/{ui,shared}/` + `lib/` + `stores/`.**
- **UI state library: Zustand** (minimal, ~1.5 KB, persist middleware), used only for genuine UI ephemera.
- **Co-located tests: yes** (`X.tsx` + `X.test.tsx` in the same folder).

**Layout sketch:**

```
frontend/src/
├── features/ # vertical, domain-aligned slices
│ ├── auth/
│ │ ├── components/ # LoginForm, OAuthButtons, MagicLinkSent
│ │ ├── hooks/ # useCurrentUser, useLogin, useLogout
│ │ ├── routes/ # login.tsx, verify-email.tsx, accept-invite.tsx
│ │ ├── stores/ # only if feature needs its own (rare)
│ │ └── types.ts
│ ├── orgs/
│ ├── projects/
│ ├── settings/
│ └── audit/
├── components/
│ ├── ui/ # shadcn-style copy-paste primitives (per #10)
│ └── shared/ # cross-feature shared (EmptyState, ErrorBoundary, EntityHeader)
├── lib/
│ ├── api/ # custom mutator + orval-generated/
│ ├── auth/ # in-memory tokenStore, JWT decode
│ ├── theme/ # theme.ts, applyTheme.ts
│ └── utils/ # cn(), formatters, date helpers
├── stores/ # global Zustand: uiStore (theme, sidebar), toastStore
├── routes/ # TanStack Router root + layouts + error boundaries
├── styles/ # Tailwind imports, theme.css
└── main.tsx
```

**State assignment rules (strict — enforce in code review):**

| Kind of state | Where it lives |
|---------------|----------------|
| **Server data** (projects, users, audit entries) | TanStack Query — never elsewhere |
| **URL-derivable state** (current org, filters, page, tab) | TanStack Router params + search params |
| **Form state** (in-progress edits) | React Hook Form + Zod schemas |
| **UI ephemera** (theme, sidebar collapse, toast queue, modal/drawer stack) | Zustand stores in `src/stores/` |
| **Component-local one-shot state** (input draft inside one component) | `useState` |

**Why Zustand and not Redux / Jotai / Context-only:**
- The actual cross-component UI state in this app is small (~5–10 atoms: theme, sidebar, toasts, current modal). Redux Toolkit's machinery would dominate the surface; Jotai's atomic model is overkill for so few state pieces; Context with multiple providers leads to prop-drilling and re-render storms.
- Zustand: 1.5 KB, no provider, `persist` middleware for localStorage-backed values (theme, sidebar collapsed), trivial to test.

**Why hybrid (and not feature- or layer-only):**
- Pure feature-folders force every shared primitive into a feature it doesn't belong to.
- Pure layer-folders scatter "auth" across 5 directories — slow to onboard, slow to delete.
- Hybrid: domain code is co-located in `features/`; truly shared UI primitives live in `components/ui/`; cross-cutting infrastructure in `lib/`.

**Co-located tests:**
- `LoginForm.tsx` + `LoginForm.test.tsx` in `features/auth/components/`.
- E2E (Playwright) lives in `frontend/e2e/` — separate from per-component tests.
- Matches the GIVEN/WHEN/THEN convention (already in `platform/CLAUDE.md`).

**Output:** ADR (likely **ADR-011 — Frontend project layout & state assignment**) — small but worth pinning so subsequent UI sub-issues don't re-litigate.

**Open sub-questions:**
- Stories for `components/ui/` — Storybook vs Ladle vs none. Defer to #10 (component library variant).
- Naming: `features/auth/` vs `auth/` (no prefix). Locked: keep the `features/` prefix; explicit beats implicit.

---

### 10. Component library variant 🟩
**Question:** which UI component set, plus how the design system surfaces to end-users (Storybook, theme picker, brand customisation).

**Decision:** **shadcn/ui canonical** — components, blocks, and charts from the official registry — combined with a **phased plan** for design-system-as-product-feature.

**Stack lock:**
- **Component library:** shadcn/ui (official, https://ui.shadcn.com/) — components + blocks + charts from one registry.
- **Underlying:** Radix UI primitives + Tailwind CSS **v4** + Class Variance Authority (already in ADR-004).
- **No Tremor** — shadcn-charts cover dashboards; revisit only if a need shadcn cannot serve appears.
- **No Park UI / Catalyst / Mantine / MUI** — would break the Radix-based foundation or introduce npm-package model.

**Initial component set for bootstrap (#2 in platform):**

```bash
npx shadcn@latest add \
 button input label form select textarea checkbox radio-group switch \
 dialog sheet alert-dialog popover dropdown-menu tooltip toast \
 card badge avatar separator skeleton tabs accordion \
 table calendar
```

(~22 primitives — covers auth, settings, dashboard, data tables, forms, dialogs.)

**Initial blocks:**
- `login-04` (or chosen variant) for authentication pages.
- `sidebar-07` (or chosen variant) for the dashboard layout shell.

**Phased design-system-as-feature:**

| Phase | What ships | When |
|-------|-----------|------|
| **Phase 1 (epic #16)** | `organisations.theme JSONB` column + 3–5 pre-defined themes (Default, Modern, Corporate, Dark, High-contrast) + simple `<ThemePicker>` in Settings | Bootstrap and beyond, this epic |
| **Phase 2 (new epic, after #16)** | `/admin/design-system` admin page — embedded component catalogue + visual theme editor (color sliders, radius, font) + live preview + save-as-org-brand | Separate "Brand Customisation" epic, post-#16 |
| **Phase 3 (optional, dev-only)** | Storybook on `localhost:6006` for component development | When ≥ 20 custom (non-shadcn) components exist; not required for SaaS-core |
| **Phase 4 (FASTSAAS, far future)** | Public Storybook on `design.fastsaas.dev` + Chromatic visual regression | When/if FASTSAAS becomes a public design-system product |

**Storybook (in v1 SaaS-core): not used.** shadcn's canonical catalogue at https://ui.shadcn.com replaces the need for an internal one until we have a meaningful number of FASTSAAS-specific components.

**Custom registry (future):** when FASTSAAS-specific components emerge (`PropertyCard`, `ScenarioComparison`, `LeaseEditor`, …), publish them as a shadcn-compatible registry at e.g. `design.fastsaas.com/registry/...` so pilots and projects can `npx shadcn add <url>`. This is a Phase 2/3 concern, not v1.

**Rationale:**
- shadcn is the largest, most AI-tooling-aligned component ecosystem; matches our Vibe Coding strategy.
- shadcn-charts inclusion eliminates the previously-planned Tremor dependency.
- The phased design-system rollout lets us ship #16 without building a full admin design page, while still laying the **right foundation** (`organisations.theme` column, CSS variables, simple picker) so Phase 2 is additive, not a refactor.
- Custom-built `/admin/design-system` (Phase 2) is strategically more valuable than embedded Storybook because it integrates auth, RBAC, multi-tenancy, and per-org theme persistence natively — turning the design system into a product feature, not a developer tool.

**Trade-offs accepted:**
- We maintain a shadcn registry of components in our repo by hand (canonical updates require manual diff review). Acceptable for the value of full code ownership.
- Tailwind v4 chosen over v3 — small risk of edge-case shadcn incompatibility; mitigated by sticking to canonical components and watching shadcn release notes.

**Output:** ADR (likely **ADR-012 — UI: shadcn + phased design-system-as-feature**) + a follow-up backlog item for the Phase 2 epic ("Brand Customisation — design-system admin page + per-org theme persistence").

**Open sub-questions for bootstrap:**
- Specific shadcn fork/version pin for Tailwind v4 — verify at install time; canonical now supports v4.
- Pre-defined theme names and palettes — design exercise (probably copy 3–5 from `https://ui.shadcn.com/themes` initially).

---

## Cross-cutting layout proposal (preview, refined as decisions land)

```
platform/
├── backend/
│ ├── src/fastsaas/
│ │ ├── core/ # actors, auth, jwt, intent_hash, audit middleware
│ │ ├── tenants/ # organisations, projects, members, RLS helpers
│ │ ├── api/ # FastAPI routers
│ │ └── workers/ # background jobs (per decision #1)
│ ├── alembic/
│ └── tests/
└── frontend/
 └── src/
 ├── features/{auth,orgs,projects,settings,audit}/
 ├── components/ui/ # shadcn-style components
 ├── lib/{api,auth,theme}/
 └── routes/ # TanStack Router
```

(Refined per decision #9.)

---

## Open questions in `fastsaas/requirements/open-questions/` to resolve here

- `Resource Limits.md` — partially in scope (quota fields on `organisations`). Full FASTSAAS answer in epic #2.
- `Result Storage Format.md` — out of scope (FASTSAAS-specific). Note in design as "deferred to #2".
- Others as discovered.

---

## ROUND 2 — gap discovered: access model under-specified

After the first 10 decisions were locked, we surfaced 7 use cases (`requirements/formal/use-cases/UC-001..UC-010`) that materially exceed the access model implied by the spike. In particular:

- **UC-001** — practitioner shares read-only project with a non-member client.
- **UC-002** — large org with multiple isolated departments.
- **UC-003** — personal AGENT (Claude/Cursor via MCP) acting on behalf of HUMAN with explicit scope.
- **UC-004** — AI Command Bar (HUMAN action via LLM-translated intent).
- **UC-005** — bulk pipeline SERVICE acting org-wide on automated schedule.
- **UC-007** — SERVICE actor without HUMAN parent (third actor type).
- **UC-010** — Org-wide policy on what AGENT/SERVICE capabilities are allowed.

These cases expose three gaps:

1. **Hierarchy:** spike assumes 2-level `Org → Project`. UC-002 demands `Org → Department → Project`.
2. **Actor types:** ADR-009 has only HUMAN + AGENT. UC-005, UC-007 demand SERVICE.
3. **Authorization model:** spike loosely mentions "owner / admin / member / viewer roles" but never specifies the underlying mechanism. Per-project guest (UC-001), AGENT-bounded scope (UC-003), policy-on-capabilities (UC-010) cannot be satisfied with pure RBAC.

A research note (`requirements/reference/access-model-rbac-vs-capability.md`) compares pure RBAC, capability-based, and hybrid approaches across all UCs. **Hybrid wins on 7/9 scenarios.** Industry analogues (AWS IAM, GCP IAM, GitHub, Linear, HashiCorp Vault, K8s RBAC) all converge on hybrid.

The following decisions revise/extend Round 1:

---

### 11. Authorization model 🟩

**Question:** how to express, provision, check, and govern who can do what across HUMAN, AGENT, SERVICE actors.

**Decision:** **Hybrid — capabilities as the underlying primitive; role bundles as presentation layer.**

**Mechanics:**

- A `capabilities` table holds rows of `(actor_id, operation, resource_type, resource_id, conditions, bundle_name, granted_by, granted_at, expires_at, revoked_at, policy_blocked, metadata)`. Schema in `requirements/reference/access-model-rbac-vs-capability.md` § 4.
- A capability check is the only authorization mechanism. Code calls `can(actor, op, resource)` → boolean. RLS (per ADR-007) remains the DB-side guarantee; capability is the application-side gate.
- Default role bundles (`role:owner`, `role:admin`, `role:member`, `role:viewer`, `role:dept_lead`, `role:dept_member`, `role:guest_viewer`, `role:compliance_officer`) defined in code. Assigning a role mints all its capabilities tagged with `bundle_name`. Changing role revokes the old bundle + mints the new.
- One-off shares (UC-001 guest, UC-003 AGENT scope) mint capabilities directly without a bundle (or with `bundle_name='role:guest_viewer'` for UI display).
- Org-wide policies (UC-010) are filters applied at capability **provisioning** AND at runtime check. A capability that violates an active policy is `policy_blocked=true`.

**Operation vocabulary (locked for v1):** `read`, `write`, `delete`, `run` (model execution), `admin` (settings, schema), `share` (grant capabilities to others), `grant` (mint capabilities for AGENTs).

**Resource types (locked for v1):** `organisation`, `department`, `project`, `scenario`, `audit_log`, `agent`, `service`. Wildcard `*` reserved for system roles.

**Audit:** every capability use writes an audit row (per ADR-010) with `intent_metadata.capability_id` referencing the capability that authorised the action.

**Output:** ADR-013 (Authorization model) — to be created post-spike-merge.

---

### 12. Hierarchy — extend to Org → Department → Project 🟩

**Question:** is two-level (`Org → Project`) sufficient?

**Decision:** **No. Extend to three-level: `Org → Department → Project`.**

**Mechanics:**

- New table `departments`: `(id, organisation_id, name, description, created_at, deleted_at)`.
- New table `department_members`: `(department_id, actor_id, role, created_at)` where role ∈ `{dept_lead, dept_member}`.
- `projects` gains `department_id NOT NULL` (FK to `departments`).
- For small orgs auto-create a `Default` department on org creation; UI hides department-switching when only one exists.
- RLS context extended (per updated ADR-007): `SET LOCAL app.current_org` AND `SET LOCAL app.current_department`.
- Cross-department transfer: `UPDATE projects SET department_id = ? WHERE id = ?` with target dept-lead approval flow.
- Cross-department guest: capability with `resource_id=project.id` regardless of viewer's dept membership (per UC-002 [A3]).

**Output:** ADR-014 (Hierarchy: Org → Department → Project).

---

### 13. Actor types — add SERVICE 🟩

**Question:** is HUMAN + AGENT enough?

**Decision:** **No. Add `SERVICE` actor type for org-owned automation accounts (UC-005, UC-007).**

**Mechanics:**

- `actors.actor_type` CHECK constraint extended: `actor_type IN ('HUMAN', 'AGENT', 'SERVICE')`.
- New child table `services`: `(actor_id, organisation_id, owner_actor_id, api_key_hash, description, last_used_at)`. `owner_actor_id` is the responsible HUMAN (for notifications), **not** parent (so SERVICE survives HUMAN departure).
- SERVICE has `parent_actor_id IS NULL`. New CHECK: `service_no_parent CHECK (actor_type <> 'SERVICE' OR parent_actor_id IS NULL)`.
- SERVICE cannot have admin-level capabilities (`admin:org`) — enforced as default policy.
- SERVICE has API key only — no UI login.
- Audit shows SERVICE distinctly: `actor_type=SERVICE`, display via `services.description`.

**Output:** ADR-015 (Actor types: SERVICE addition; supersedes the relevant section of ADR-009).

---

### 14. Org policy on capabilities 🟩

**Question:** mechanism for org-wide governance of AGENT/SERVICE behaviour.

**Decision:** **Org-level policies — declarative rules limiting what capabilities can be provisioned and exercised, with explicit audit and override flow.**

**Mechanics (v1 scope minimal):**

- `org_policies` table: `(id, organisation_id, name, description, rule_json, priority, created_by, created_at, deleted_at)`. `rule_json` is a structured rule (no DSL in v1; admin-friendly form in UI).
- Enforcement: at capability provisioning AND on every runtime check, applicable policies evaluated; capability marked `policy_blocked=true` or denied.
- Audit: every policy change captured; every policy-driven denial captured.
- Override: org owner can issue time-limited override (TTL ≤ 1 h) with heavy audit (Slack alert, email).
- v1 ships: data model + simple "deny capability of type X" policy + UI for managing policies + audit. Threshold-based and time-window policies (UC-010 [A1], [A2]) — Phase 2.

**Output:** ADR-016 (Org policy mechanism).

---

### 15. API Keys 🟩

**Question:** how programmatic actors (HUMAN scripting, AGENT via MCP, SERVICE for cron/CI) authenticate against the API; how keys are created, used, rotated, revoked.

**Decision:** **Separate `api_keys` table with multiple keys per actor; opaque prefixed tokens; SHA-256 storage; per-key optional scope restriction; soft-revoke; rotation grace period.**

**Token format:**

```
apz_<actor_type>_<43-char-base62>

Examples:
 apz_human_8f3cVKtLm9pQRwzN2xYbHsT3uE6FjZ4dWqX1bYn7aP5v
 apz_agent_a91krNxB3vYsTuPpJgQ4MdH7eKzL2cXiVqR5fW8nE6mZ
 apz_service_zz72YpQwL3bKcVnXmJ4fH9rG6tDsNvU5aE1iZ8oW7xT
```

- 32 bytes random → base62 (~43 chars).
- Prefix carries actor type — debugging, secret scanning, log filtering.
- Total ~55 chars; 256-bit entropy.

**Schema:**

```sql
CREATE TABLE api_keys (
 id UUID PRIMARY KEY, -- UUID v7
 actor_id UUID NOT NULL REFERENCES actors(id),
 key_hash TEXT NOT NULL UNIQUE, -- sha256(token), optionally salted
 key_prefix TEXT NOT NULL, -- 'apz_agent_8f3c' for display
 name TEXT NOT NULL,
 scope_restriction JSONB DEFAULT NULL, -- optional capability subset; NULL = inherit all
 
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 created_by UUID NOT NULL REFERENCES actors(id),
 
 last_used_at TIMESTAMPTZ NULL,
 last_used_ip INET NULL,
 
 expires_at TIMESTAMPTZ NULL, -- optional TTL
 revoked_at TIMESTAMPTZ NULL,
 revoked_by UUID REFERENCES actors(id),
 revoked_reason TEXT NULL, -- 'rotated' | 'compromised' | 'unused' | 'manual'
 rotation_grace_until TIMESTAMPTZ NULL, -- during rotation, both old + new valid until this
 
 metadata JSONB DEFAULT '{}' -- {client_hint, ip_allowlist, rate_limit,...}
);

CREATE UNIQUE INDEX idx_keys_hash ON api_keys (key_hash) WHERE revoked_at IS NULL;
CREATE INDEX idx_keys_actor ON api_keys (actor_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_keys_prefix ON api_keys (key_prefix);
```

**Refinement to ADR-009:**

The Round 1 ADR-009 had `agents.api_key_hash` and `services.api_key_hash` (one key per actor). **Removed.** API keys now live in the dedicated `api_keys` table — multiple keys per actor, per-key scope, per-key audit.

**Authentication flow:**

1. Client: `Authorization: Bearer apz_<type>_<random>`
2. Auth middleware: format check (regex) → sha256 → Redis cache → DB lookup if miss → load actor.
3. Set request context: `actor_id`, `api_key_id`, `key_scope`.
4. Set RLS context (per ADR-007): `app.current_org`, `app.current_department`.
5. Capability check (per Decision #11): `effective = actor.capabilities ∩ key.scope_restriction`.
6. Audit row carries `intent_metadata.api_key_id` — per-key replay.

**Per-key scope restriction:**

A key may carry a strict subset of its actor's capabilities. Effective capabilities at request time = `actor.capabilities ∩ key.scope_restriction` (when restriction present). Cannot escalate via key.

Use cases:
- HUMAN creates a read-only personal key for a Jupyter notebook.
- AGENT key restricted to one department (per UC-008 [A2]).
- SERVICE key with rate-limit restriction.

**Lifecycle:**

- **Create:** generated, full token shown ONCE, sha256 stored.
- **Use:** as auth header; updates `last_used_at` and `last_used_ip` async.
- **Rotate:** mints new key; old `rotation_grace_until = NOW + 7d` (default; org-policy-configurable). After grace — auto-revoke.
- **Revoke:** soft-revoke (`revoked_at` + `revoked_reason`); Redis cache invalidated immediately. Hash retained for audit and detecting reuse-after-revocation.
- **Cascade revoke:** when actor soft-deleted, all their keys revoked.

**Security policies (per Decision #14):**

Org policies may enforce:
- Max keys per actor.
- Required expiry (no `expires_at=NULL` allowed).
- IP allowlist required for SERVICE keys.
- Forced rotation interval.

**Audit:**

Every action via API key writes audit (per ADR-010) with `intent_metadata.api_key_id`. Reports:
- "Show all actions by key X."
- "Detect use of revoked keys" (post-revocation attempts → high-priority alert).
- "Keys created > N days ago, used from new IP" (anomaly detection).

**Rationale:**

- Multiple keys per actor → realistic (laptop + desktop + CI; rotation needs concurrent old + new).
- Per-key scope restriction → defense-in-depth (compromised key has narrower blast radius than compromised actor).
- Per-key audit → critical for incident response (which key acted, when, from where).
- Prefix-based token format → secret scanning compatibility (GitHub Secret Scanning partner program target post-public-launch).
- Soft-revoke → forensic value preserved.

**Output:** ADR-017 (API Keys) + amendment to ADR-009 (remove `api_key_hash` from `agents` and `services`).

**Open sub-questions:**
- Salt sha256 with per-deployment secret? *Lean toward yes (paranoid best practice).*
- HUMAN keys in v1 SaaS-core or Phase 2? *Lean toward v1 — same flow as AGENT/SERVICE.*
- IP allowlist UI in v1 or Phase 2? *Schema in v1; full UI Phase 2.*
- `_test_` / `_live_` prefix env distinction (Stripe-style)? *Phase 2.*
- GitHub Secret Scanning partnership? *Post-public-launch.*

---

---

### Updated ADRs (Round 2)

These existing ADRs require revision to reflect Round 2 decisions:

- **ADR-007 (RLS):** add `app.current_department` context; add policy describing department isolation; add note that `audit_log` admin reads can be scoped to compliance role.
- **ADR-009 (actors):** add SERVICE actor type; add `services` child table; add CHECK constraints for parent rules per actor_type.

These will be amended (not superseded) — same ADR file, "amended" entry in changelog, status remains Accepted.

---

## Summary of Round 2

Round 2 surfaces a more honest access model:

```
Hierarchy: Org → Department → Project (was Org → Project)
Actor types: HUMAN, AGENT, SERVICE (was HUMAN, AGENT)
Authorization: capabilities + role bundles (was undefined; mentioned roles only)
Governance: org-wide policies on capabilities
```

The 7 sub-issues under #16 in `platform` need acceptance-criteria tweaks. Most relevant:
- **#2 Bootstrap** — schema includes `capabilities`, `departments`, `department_members`, `services`, `org_policies`.
- **#3 Identity** — capability provisioning at register / accept-invite.
- **#4 Tenants** — rename to "Multi-tenant hierarchy + access model"; covers departments + capabilities.
- **#5 Audit** — `intent_metadata.capability_id` reference.

Updated ADRs to write post-merge: ADR-013, ADR-014, ADR-015, ADR-016 + amendments to ADR-007 + ADR-009.
