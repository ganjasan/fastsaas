---
title: Multi-tenant orgs + capability-based access
status: in_progress
linked_issue: ganjasan/fastsaas#3
created: 2026-05-03
traces_to:
  adr:
    - "[[ADR-006_primary-keys-and-cascade]]"
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  use_cases:
    - "UC-001 (per-project guest)"
  spike: platform-saas-core-architecture-spike
  blocks:
    - "ganjasan/fastsaas#4"   # Audit middleware needs tenant context
    - "ganjasan/fastsaas#5"   # Dashboard needs org navigation
    - "ganjasan/fastsaas#7"   # E2E needs create-resource flow
---

## Why

`fastsaas` has a working identity layer (HUMAN registration, JWT, refresh, OAuth) but every authenticated user lands on an empty platform — there are no organisations, no projects, no membership, no access checks. RLS *policies* exist (migration `0002_rls_policies`) but no RLS-scoped tables.

Three blocked sub-issues sit on top of this gap:

- **#4 Audit middleware** needs `app.current_org` set per request to attribute every mutation to a tenant.
- **#5 Dashboard layouts** need an org-switcher and "create project" flow to be more than a marketing shell.
- **#7 Playwright baseline** is "Login → Create resource" — there is no resource to create.

ADR-013 already locked the access model (capabilities + role bundles); this change is the implementation. Hierarchy is two-level — `Org → Project` — per the rejection of Decision #12 (no Department entity).

## What Changes

**NEW** Postgres tables (alembic `0004_orgs_projects_membership`):
- `organisations(id, name, slug, theme, created_at, deleted_at)` — slug unique, used in URLs.
- `projects(id, organisation_id, name, slug, created_at, deleted_at)` — slug unique within org.
- `organisation_members(organisation_id, actor_id, created_at)` — membership existence; role information lives in capabilities.
- `capabilities(id, actor_id, operation, resource_type, resource_id, conditions, bundle_name, granted_by, granted_at, expires_at, revoked_at, policy_blocked, metadata)` per ADR-013.
- RLS policies on `organisations`, `projects`, `organisation_members`, `capabilities` per ADR-007.

**NEW** Backend ORM + service layer (`backend/src/fastsaas/tenants/`):
- SQLModel classes for the four tables.
- `OrganisationService` — create org (mints `role:owner` capabilities to creator), list user's orgs, soft-delete.
- `ProjectService` — create project, list projects in current org, soft-delete.
- `MembershipService` — invite to org (issues `org_invitation` magic-link reusing existing infra), accept-invite (mints `role:member` bundle), remove member, change role.

**NEW** Authorization core (`backend/src/fastsaas/authz/`):
- `can(actor, op, resource_type, resource_id) -> bool` — single authorization API per ADR-013.
- Role bundle definitions in code: `role:owner`, `role:admin`, `role:member`, `role:viewer`, `role:guest_viewer`, `role:compliance_officer`.
- `mint_bundle(actor, bundle_name, scope)` / `revoke_bundle(actor, bundle_name)` — capability provisioning helpers.
- Redis cache of materialised capabilities per actor (5-minute TTL); invalidated on grant/revoke.
- FastAPI dependencies — `require_capability(op, res_type)`, `require_org_membership`.

**NEW** Tenant context middleware:
- After `current_actor` resolves, `tenant_context` reads `X-Org: <slug>` header (or session-pinned org) and:
  - Verifies actor is a member of that org.
  - `SET LOCAL app.current_org = <uuid>` per ADR-007.
  - Attaches `org` to request state.
- Endpoints scoped to `/org/{slug}/...` use this implicitly; auth endpoints opt out.

**NEW** API endpoints (under `/api/`):
- `POST /orgs` — create org; the caller becomes owner.
- `GET /orgs` — list orgs the caller is a member of.
- `GET /orgs/{slug}` — org detail.
- `POST /orgs/{slug}/members/invite` — invite by email; magic-link sent.
- `POST /orgs/{slug}/members/accept` — accept invite (token in body); mints `role:member`.
- `DELETE /orgs/{slug}/members/{actor_id}` — remove member; revokes bundle.
- `PATCH /orgs/{slug}/members/{actor_id}` — change role (admin/member/viewer).
- `POST /orgs/{slug}/projects` — create project.
- `GET /orgs/{slug}/projects` — list projects in org.
- `GET /orgs/{slug}/projects/{project_slug}` — project detail.
- `POST /orgs/{slug}/projects/{project_slug}/share` — UC-001 per-project guest mint (recipient need not be org member).

**NEW** Frontend (`frontend/src/features/orgs/`, `frontend/src/features/projects/`):
- Org switcher in shell (Zustand `currentOrgSlug`).
- "No orgs yet" empty state on first login → "Create org" CTA.
- Org settings page (members list, invite form, role change).
- Project list + create project dialog.
- TanStack Router routes: `/orgs`, `/orgs/$slug`, `/orgs/$slug/settings/members`, `/orgs/$slug/projects/$projectSlug`.

**NEW** orval regen — generated TS hooks for the new endpoints.

## Out of scope (deferred)

- API keys (ADR-017) — separate change once `capabilities` table is settled.
- Org policies (ADR-016) — same.
- AGENT/SERVICE actor registration — MCP epic.
- Compliance officer cross-tenant audit reads — ships with #4 (audit middleware).
- Per-org theme JSONB UI (`organisations.theme`) — schema column shipped here, theme picker UI is part of #5.
- Custom role bundles per-org — Phase 2 per ADR-013 open questions.
- Capability-detail admin view (advanced UI showing raw capabilities) — Phase 2.
