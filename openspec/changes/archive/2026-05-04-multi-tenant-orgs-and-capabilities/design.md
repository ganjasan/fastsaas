---
title: Multi-tenant orgs + capability-based access — design
status: draft
linked_issue: ganjasan/fastsaas#3
created: 2026-05-03
traces_to:
  adr:
    - ADR-006
    - ADR-007
    - ADR-013
  use_cases:
    - UC-001
---

# Design

## Context

Identity layer (HUMAN actors, JWT, refresh) is shipped. RLS policies (`0002`) sit on tables that don't yet exist. ADR-013 locked capability-based access; ADR-007 locked RLS; ADR-006 locked UUID v7 + soft-delete. Hierarchy is `Org → Project` (Decision #12 was rejected — no Department).

## D1. Schema state and the 0004 delta

`0001_initial_schema` already created the full set of bootstrap tables (`organisations`, `projects`, `organisation_members`, `capabilities`, `audit_log`, `api_keys`, `org_policies`). `0002_rls_policies` already enabled RLS on `organisations`, `projects`, `org_policies`, and `audit_log`, plus granted base privileges to `app_user`.

**Gaps this change closes (alembic `0004_orgs_slugs_and_member_rls`):**

1. `organisations.slug CITEXT` — pre-launch DB is empty, so we add `NOT NULL`, a regex `CHECK` (`^[a-z0-9-]{3,63}$`), and a `UNIQUE` constraint in one revision. No backfill needed.
2. `projects.slug CITEXT` — same pattern, `UNIQUE (organisation_id, slug)`.
3. RLS on `organisation_members` — tenant_isolation policy on `organisation_id`. Membership is tenant-scoped data; defense-in-depth applies (an actor must not list members of an org they did not pin in `app.current_org`).
4. RLS on `capabilities` — two policies: `actor_self_read` (an actor always sees their own capabilities, regardless of pinned org) and `org_admin_scope` (when `app.current_org` is pinned, capabilities with matching `metadata.org_id` are also visible). Mutations are not RLS-gated — they go through application-layer `mint_*`/`revoke_*` services.
5. `app.current_actor` `SET LOCAL` — the tenant-context middleware sets this in addition to `app.current_org`, so the `actor_self_read` policy works without round-trip to `current_setting('app.current_org')`.

**Pre-existing baseline (already in place from 0001/0002, kept verbatim):**

```sql
-- 0001 (excerpt)
CREATE TABLE organisations (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT NOT NULL,
  theme        JSONB NOT NULL DEFAULT '{}'::jsonb,
  quota        JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at   TIMESTAMPTZ NULL
);
CREATE TABLE organisation_members (
  organisation_id  UUID NOT NULL REFERENCES organisations(id),
  actor_id         UUID NOT NULL REFERENCES actors(id),
  role             TEXT NOT NULL,                          -- denormalised bundle name (UI hint)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organisation_id, actor_id),
  CONSTRAINT org_member_role_valid
    CHECK (role IN ('owner','admin','member','viewer','compliance_officer'))
);
CREATE TABLE projects (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organisation_id  UUID NOT NULL REFERENCES organisations(id),
  name             TEXT NOT NULL,
  description      TEXT,
  created_by       UUID NOT NULL REFERENCES actors(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ NULL
);
CREATE TABLE capabilities (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id        UUID NOT NULL REFERENCES actors(id),
  operation       TEXT NOT NULL CHECK (operation IN
                    ('read','write','delete','run','admin','share','grant')),
  resource_type   TEXT NOT NULL CHECK (resource_type IN
                    ('organisation','project','scenario','audit_log','agent','service','*')),
  resource_id     UUID NULL,
  conditions      JSONB NOT NULL DEFAULT '{}'::jsonb,
  bundle_name     TEXT NULL,
  granted_by      UUID REFERENCES actors(id),
  granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NULL,
  revoked_at      TIMESTAMPTZ NULL,
  policy_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
  metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);
```

Notes:

- `organisation_members.role TEXT` shipped in 0001 as a denormalised display name. **Authorization enforcement remains capability-only.** The column is the same value as `capabilities.bundle_name` for the actor's primary bundle in this org, used by the members table UI to render "Owner / Admin / Member / Viewer" without joining capabilities. It is updated by the membership service whenever a bundle changes.
- `audit_log` already has a compliance-officer escape hatch in 0002 (`current_setting('app.role') = 'compliance_officer'`); we reuse that path when listing audit cross-org for compliance reads.
- `capabilities.metadata.org_id` is set by `mint_bundle` so the org-admin RLS policy can match.

### 0004 SQL sketch

```sql
-- slug on organisations
ALTER TABLE organisations
  ADD COLUMN slug CITEXT NOT NULL,
  ADD CONSTRAINT org_slug_format CHECK (slug ~ '^[a-z0-9-]{3,63}$');
CREATE UNIQUE INDEX idx_orgs_slug ON organisations (slug);

-- slug on projects
ALTER TABLE projects
  ADD COLUMN slug CITEXT NOT NULL,
  ADD CONSTRAINT project_slug_format CHECK (slug ~ '^[a-z0-9-]{3,63}$');
CREATE UNIQUE INDEX idx_projects_org_slug ON projects (organisation_id, slug);

-- RLS: organisation_members
ALTER TABLE organisation_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE organisation_members FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON organisation_members
  USING      (organisation_id = current_setting('app.current_org', true)::uuid)
  WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid);

-- RLS: capabilities (split: actor self-read + org-admin read)
ALTER TABLE capabilities ENABLE ROW LEVEL SECURITY;
ALTER TABLE capabilities FORCE ROW LEVEL SECURITY;
CREATE POLICY actor_self_read  ON capabilities
  FOR SELECT
  USING (actor_id = current_setting('app.current_actor', true)::uuid);
CREATE POLICY org_admin_scope  ON capabilities
  FOR SELECT
  USING (metadata->>'org_id' = current_setting('app.current_org', true));
CREATE POLICY app_writes ON capabilities
  FOR INSERT WITH CHECK (TRUE);   -- mint via app service; actor_id set explicitly
CREATE POLICY app_updates ON capabilities
  FOR UPDATE USING (TRUE);        -- revoke via app service; bounded by service code
```

## D2. Role bundles (in code)

```python
# backend/src/fastsaas/authz/bundles.py
BUNDLES: dict[str, list[CapabilityTemplate]] = {
    "role:owner": [
        Cap("admin",  "organisation", scope="self"),
        Cap("share",  "organisation", scope="self"),
        Cap("admin",  "project",      scope="all_in_org"),
        Cap("read",   "audit_log",    scope="self"),
        Cap("grant",  "agent",        scope="self"),
        Cap("grant",  "service",      scope="self"),
    ],
    "role:admin": [
        Cap("admin", "project",  scope="all_in_org"),
        Cap("share", "project",  scope="all_in_org"),
        Cap("read",  "audit_log", scope="self"),
    ],
    "role:member": [
        Cap("read",  "organisation", scope="self"),
        Cap("write", "project",      scope="all_in_org"),
        Cap("run",   "project",      scope="all_in_org"),
    ],
    "role:viewer": [
        Cap("read", "organisation", scope="self"),
        Cap("read", "project",      scope="all_in_org"),
    ],
    "role:guest_viewer": [
        Cap("read", "project", scope="resource"),         # resource_id required
    ],
    "role:compliance_officer": [
        Cap("read", "audit_log", scope="self"),
    ],
}
```

`scope` is resolved at mint time:
- `"self"` → `resource_id = current_org.id` (for `organisation` / `audit_log`).
- `"all_in_org"` → one capability row per existing project; subsequent project create issues additional rows for active member bundles (project lifecycle hook).
- `"resource"` → caller passes explicit `resource_id`.

Trade-off: `"all_in_org"` materialises N rows per member per project. For org with 100 members × 50 projects × 3 bundle entries = 15 000 rows. Index keeps `can()` sub-millisecond; cache hides the count. Alternative ("type-wide grant with `resource_id=NULL`, scoped by membership") was considered but rejected — it would require special-casing every check, defeating the point of "capability is the only API".

## D3. `can()` API

```python
# backend/src/fastsaas/authz/check.py
async def can(
    actor_id: UUID,
    operation: Operation,
    resource_type: ResourceType,
    resource_id: UUID | None = None,
    *,
    db: AsyncSession,
    cache: Redis,
) -> bool:
    caps = await _load_actor_caps(actor_id, db, cache)        # cached set
    return any(
        c.operation == operation
        and c.resource_type == resource_type
        and (c.resource_id is None or c.resource_id == resource_id)
        and not c.is_expired()
        and not c.policy_blocked
        for c in caps
    )
```

Cache key: `caps:{actor_id}` → JSON list, 5-min TTL. Invalidated by `mint_bundle` / `revoke_bundle` / `mint_capability` / `revoke_capability`. Stampede guard: SETNX lock on miss.

## D4. Tenant context middleware

```python
# backend/src/fastsaas/tenants/middleware.py
@app.middleware("http")
async def tenant_context(request, call_next):
    if request.url.path.startswith(("/auth", "/health", "/openapi")):
        return await call_next(request)

    actor = request.state.actor          # set by identity middleware
    org_slug = request.headers.get("X-Org") or request.cookies.get("fastsaas_org")
    if not org_slug:
        return await call_next(request)  # endpoint may opt-in via require_org

    org = await _resolve_org_membership(actor.id, org_slug)
    if org is None:
        raise HTTPException(404, code="org.not_found_or_forbidden")  # ADR-007 don't leak existence

    async with db.begin() as tx:
        await tx.execute(text("SET LOCAL app.current_org = :id"), {"id": str(org.id)})
        await tx.execute(text("SET LOCAL app.current_actor = :id"), {"id": str(actor.id)})
        request.state.org = org
        return await call_next(request)
```

`require_org` dependency mandates `request.state.org`; routes in `/api/orgs/{slug}/...` add it implicitly.

## D5. Provisioning flows

| Flow | Effect |
|---|---|
| `POST /orgs` | Insert `organisations`, `organisation_members`, mint `role:owner` for caller. All in one transaction. |
| `POST /orgs/{slug}/members/invite` | Issue `org_invitation` magic-link (existing infra, 7-day TTL). No capability minted yet. |
| `POST /orgs/{slug}/members/accept` | Validate token, insert `organisation_members`, mint `role:member` (default; admin can `PATCH` later). |
| `PATCH /orgs/{slug}/members/{actor_id}` | Revoke previous bundle, mint new bundle. Audit row per ADR-010. |
| `DELETE /orgs/{slug}/members/{actor_id}` | Remove `organisation_members` row, revoke all bundles for that actor in this org (`metadata.org_id = ...`). |
| `POST /orgs/{slug}/projects` | Insert `projects`. For every active org member bundle that needs `all_in_org` scope (owner/admin/member/viewer), mint capability rows for the new project. |
| `POST /orgs/{slug}/projects/{slug}/share` | UC-001 — invite by email; recipient may be a non-member. Issues `org_invitation`-like magic-link with `purpose='project_share'` (new value). On accept, mint `role:guest_viewer` with `resource_id = project.id`. No `organisation_members` row created. |

## D6. Per-project guest (UC-001)

Guest is a HUMAN actor with one capability: `read:project[resource_id=X]`. They have no `organisation_members` row, so org navigation does not surface the org. They can still log in (HUMAN actor) and visit `/orgs/{slug}/projects/{project_slug}` directly via the share link; tenant_context middleware accepts the request because the capability exists, even without org membership — the special case is gated by the explicit guest path:

- `tenant_context` allows missing `organisation_members` if `can(actor, 'read', 'project', any_in_org)` returns true.
- Guest flow uses `app.current_org` from the project's parent org so RLS works.

## D7. Migration strategy

Pre-launch repo. Single migration `0004_orgs_projects_membership` adds all four tables + RLS policies. No backfill. Follow-up changes (audit middleware, api_keys) layer on top without touching `0004`.

## D8. Open questions

- **Org slug squat protection** — first-come-first-served for v1; reserved-words list (e.g. `admin`, `api`, `auth`) committed in code. Branding / domain disputes are post-launch.
- **Role-bundle materialisation cost at scale** — see D2 trade-off; revisit with profiling once orgs cross 50 members.
- **Cross-org actor identity** — one HUMAN actor can be a member of multiple orgs (each membership row is independent). Confirm refresh-token-family and JWT carry no org claim (org pinning is per-request via `X-Org`).
- **`actor_id` index on `organisation_members`** — second index for "list my orgs" query; add in this migration, not post-hoc.

## D9. Test strategy

- Unit — `can()` matrix (all bundles × all ops × all resource types); bundle mint/revoke; cache invalidation.
- Integration — RLS denies cross-tenant SELECT under `app_user` role; `BYPASSRLS` migrator role bypasses.
- E2E (deferred to #7) — register → create org → invite member → member accepts → both see same project.

## D10. Frontend layout

```
frontend/src/features/
├── orgs/
│   ├── components/
│   │   ├── OrgSwitcher.tsx
│   │   ├── CreateOrgDialog.tsx
│   │   ├── MembersTable.tsx
│   │   └── InviteMemberDialog.tsx
│   ├── hooks/
│   │   ├── useCurrentOrg.ts
│   │   └── useMyOrgs.ts
│   ├── routes/
│   │   ├── orgs.tsx
│   │   ├── orgs.$slug.tsx
│   │   ├── orgs.$slug.settings.members.tsx
│   │   └── orgs.new.tsx
│   └── types.ts
└── projects/
    ├── components/
    │   ├── ProjectList.tsx
    │   └── CreateProjectDialog.tsx
    ├── hooks/useProjects.ts
    └── routes/
        ├── orgs.$slug.projects.tsx
        └── orgs.$slug.projects.$projectSlug.tsx
```

Org switcher pins selection to `localStorage` via Zustand `persist` middleware; on every API call the orval mutator injects `X-Org: <slug>`.
