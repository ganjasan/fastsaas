---
title: Multi-tenant orgs + capabilities — tasks
linked_issue: ganjasan/fastsaas#3
---

# Tasks

## 1. Migration 0004 — slug + RLS delta on existing tables

> 0001 already created `organisations`, `projects`, `organisation_members`, and `capabilities`. 0002 already wrapped `organisations` / `projects` / `org_policies` / `audit_log` with RLS. This migration only adds what 0001/0002 left out per design.md §D1.

- [x] 1.1 Generate alembic revision `0004_orgs_slugs_and_member_rls`
- [x] 1.2 ALTER `organisations`: add `slug CITEXT NOT NULL` + CHECK regex + UNIQUE INDEX
- [x] 1.3 ALTER `projects`: add `slug CITEXT NOT NULL` + CHECK regex + UNIQUE INDEX `(organisation_id, slug)`
- [x] 1.4 ENABLE/FORCE RLS on `organisation_members` + `tenant_isolation` policy on `organisation_id`
- [x] 1.5 ENABLE/FORCE RLS on `capabilities` + `actor_self_read` (FOR SELECT on `app.current_actor`) + `org_admin_scope` (FOR SELECT on `metadata->>'org_id'`) + `app_writes` (FOR INSERT) + `app_updates` (FOR UPDATE)
- [x] 1.6 Reserved-slug list seeded in app code (`backend/src/fastsaas/tenants/slugs.py`); no DB constraint
- [x] 1.7 Verify migration applies and rolls back cleanly against `make dev` Postgres (host port 5532 per FastSaaS +100 convention). `alembic upgrade head` → `downgrade 0003` → `upgrade head` succeeds; full pytest suite (109 tests) green.

## 2. ORM models — `backend/src/fastsaas/tenants/models.py`

- [x] 2.1 `Organisation` SQLModel
- [x] 2.2 `Project` SQLModel
- [x] 2.3 `OrganisationMember` SQLModel + `OrganisationRole` enum
- [x] 2.4 `Capability` SQLModel — new module `backend/src/fastsaas/authz/models.py`

## 3. Authorization core — `backend/src/fastsaas/authz/`

- [x] 3.1 `bundles.py` — BUNDLES dict per design.md §D2 with CapabilityTemplate dataclass + `Operation`/`ResourceType`/`Scope` enums + `PRIMARY_BUNDLES` set
- [x] 3.2 `service.py::mint_bundle(actor, bundle_name, *, org, project_ids?, resource_id?)` resolves scope and inserts capability rows
- [x] 3.3 `service.py::revoke_bundle(actor, bundle_name, *, org)` sets `revoked_at` on rows tagged with `metadata.org_id`
- [x] 3.4 `service.py::mint_capability` / `revoke_capability` for one-off grants
- [ ] 3.5 `cache.py` — Redis-backed `_load_actor_caps(actor_id)` with 5-min TTL + SETNX stampede guard + invalidate-on-mutate (currently a passthrough; no caching yet)
- [x] 3.6 `check.py::can(actor_id, op, res_type, res_id=None)` per design.md §D3
- [x] 3.7 `dependencies.py::require_capability(op, res_type)` FastAPI dependency
- [x] 3.8 Unit tests — bundle catalogue invariants (`test_authz_bundles.py`, 11 tests); slug validator (`test_tenants_slugs.py`, 15 tests). DB-touching matrix (mint/revoke + RLS) deferred to step 1.7-unblocked.

## 4. Tenant context dependency

> Realised as a FastAPI `Depends(tenant_context)` rather than ASGI middleware
> — keeps the same DB session as the route via per-request Depends caching,
> so `SET LOCAL` lives on the route's transaction. Org-by-slug bootstrap goes
> through a short BYPASSRLS migrator session because RLS on `organisations`
> needs `app.current_org` to be set, which we don't know until after the
> lookup itself.

- [x] 4.1 `backend/src/fastsaas/tenants/dependencies.py::tenant_context(slug)` returns `TenantContext(org, actor, is_guest)`; sets `app.current_org` + `app.current_actor` LOCAL on the request session.
- [x] 4.2 `require_org_member` dependency rejects guests for member-only routes (e.g. members listing).
- [x] 4.3 Guest path: tolerate missing `organisation_members` row when an active capability with `metadata.org_id = org.id` exists (UC-001).
- [ ] 4.4 Wire into routers — `Depends(tenant_context)` lands on every `/orgs/{slug}/...` endpoint in phases 5–8.
- [x] 4.5 Tests — `tests/test_tenants_context.py` covers: unknown slug → None; member → `is_guest=False`; non-member → None (no info leak); guest with capability → `is_guest=True`; revoked capability ignored; soft-deleted org invisible.
- [x] 4.6 `db.py` — second engine `migrator_engine` (BYPASSRLS, small pool) + `migrator_session_scope()` for the bootstrap lookup. Disposed alongside the main engine.

## 5. Org service + endpoints

- [ ] 5.1 `tenants/service.py::OrganisationService.create(name, slug, owner_actor)` — TX: insert org + members + mint `role:owner`
- [ ] 5.2 `OrganisationService.list_for_actor(actor_id)`
- [ ] 5.3 `OrganisationService.get_by_slug(slug, actor_id)` — RLS-bypassed lookup gated by membership
- [ ] 5.4 `OrganisationService.soft_delete(org_id)` — owner-only, sets `deleted_at`, revokes all bundles for the org
- [ ] 5.5 `api/orgs.py` — POST /orgs, GET /orgs, GET /orgs/{slug}, DELETE /orgs/{slug}
- [ ] 5.6 Slug validation — regex + reserved-list rejection with `code = "org.slug_reserved"` / `org.slug_invalid`
- [ ] 5.7 Tests — owner mint, RLS isolation, slug uniqueness, reserved-slug rejection

## 6. Membership service + endpoints

- [ ] 6.1 `MembershipService.invite(org, email, role)` — issues `org_invitation` magic-link (uses existing magic-link infra, purpose already supported)
- [ ] 6.2 `MembershipService.accept(token, actor)` — validates token, inserts member, mints role bundle (default `role:member`)
- [ ] 6.3 `MembershipService.change_role(actor_id, new_bundle)` — revoke + mint
- [ ] 6.4 `MembershipService.remove(actor_id)` — delete row + revoke all bundles
- [ ] 6.5 `api/orgs.py` — POST /orgs/{slug}/members/invite, POST /orgs/{slug}/members/accept, PATCH /orgs/{slug}/members/{actor_id}, DELETE /orgs/{slug}/members/{actor_id}, GET /orgs/{slug}/members
- [ ] 6.6 Email template `org-invitation.html` (jinja, `{{ app_name }}`, `{{ inviter }}`, `{{ org_name }}`, link)
- [ ] 6.7 Tests — invite + accept happy path; expired token; role change revokes old bundle; remove cascades capabilities

## 7. Project service + endpoints

- [ ] 7.1 `ProjectService.create(org, name, slug)` — insert project; loop active org member bundles and mint `all_in_org` rows for the new project
- [ ] 7.2 `ProjectService.list_in_org(org)` — RLS-scoped SELECT; filter `deleted_at IS NULL`
- [ ] 7.3 `ProjectService.get(slug, org)` — single read
- [ ] 7.4 `ProjectService.soft_delete(project_id)` — sets `deleted_at`; revokes project-scoped bundles for non-members? **No** — keep capabilities, soft-deleted project is hidden by app filter; restoration restores access naturally
- [ ] 7.5 `api/projects.py` — POST/GET/PATCH/DELETE under /orgs/{slug}/projects
- [ ] 7.6 `require_capability("write", "project")` on POST/PATCH/DELETE; `require_capability("read", "project")` on GET
- [ ] 7.7 Tests — project create mints capabilities for all members; member without write fails 403; viewer can read

## 8. Per-project guest (UC-001)

- [ ] 8.1 Add `MagicLinkPurpose.PROJECT_SHARE` enum value + alembic revision `0005_magic_link_purpose_project_share` (extends CHECK)
- [ ] 8.2 `MembershipService.invite_guest(project, email)` — magic-link with `purpose=project_share`, `metadata.project_id`
- [ ] 8.3 `MembershipService.accept_guest(token, actor)` — mints `role:guest_viewer` with `resource_id = project_id`; no `organisation_members` insert
- [ ] 8.4 `api/projects.py::POST /orgs/{slug}/projects/{project_slug}/share`
- [ ] 8.5 Email template `project-share.html`
- [ ] 8.6 Tests — guest with read capability sees the project; guest cannot list other projects; guest cannot see members; revoking guest's capability blocks access immediately (cache invalidation)

## 9. Frontend — orgs feature

- [ ] 9.1 `make codegen` regenerates orval hooks for new endpoints
- [ ] 9.2 Custom orval mutator (`src/lib/api/client.ts`) injects `X-Org: <currentOrgSlug>` from Zustand
- [ ] 9.3 `features/orgs/lib/orgStore.ts` — Zustand with persist; `currentOrgSlug`, `setCurrentOrg`
- [ ] 9.4 `features/orgs/components/OrgSwitcher.tsx` — dropdown using `useMyOrgs()`
- [ ] 9.5 `features/orgs/components/CreateOrgDialog.tsx` — react-hook-form + zod (slug live preview)
- [ ] 9.6 `features/orgs/components/MembersTable.tsx` + `InviteMemberDialog.tsx`
- [ ] 9.7 Routes — `routes/orgs.tsx` (list + empty state), `orgs.$slug.tsx` (overview), `orgs.$slug.settings.members.tsx`, `orgs.new.tsx`
- [ ] 9.8 Empty-state on `/orgs` for first-login users — CTA "Create your first org"
- [ ] 9.9 Vitest — OrgSwitcher renders with mock orgs; CreateOrgDialog validation; InviteMemberDialog submit

## 10. Frontend — projects feature

- [ ] 10.1 `features/projects/components/ProjectList.tsx`, `CreateProjectDialog.tsx`
- [ ] 10.2 Routes — `orgs.$slug.projects.tsx`, `orgs.$slug.projects.$projectSlug.tsx`
- [ ] 10.3 Project detail page placeholder ("nothing here yet" — content lands with future epics)
- [ ] 10.4 Vitest covers list + create dialog

## 11. Wiring + smoke

- [ ] 11.1 Register `tenant_context` middleware in `main.py` after identity middleware
- [ ] 11.2 Register `orgs_router` and `projects_router` in `main.py`
- [ ] 11.3 Update `frontend/e2e/smoke.spec.ts` to cover register → create org → create project → log out → log in (basic happy path; full suite is #7)
- [ ] 11.4 `make test` green — backend pytest + frontend vitest + e2e smoke
- [ ] 11.5 `make lint` green

## 12. Validation + close-out

- [ ] 12.1 `openspec validate multi-tenant-orgs-and-capabilities --strict` passes
- [ ] 12.2 `requirements/decisions/` — no new ADR (this is implementation of ADR-013); CLAUDE.md mention if any new conventions emerged
- [ ] 12.3 PR opened, linked to issue #3
- [ ] 12.4 Archive change after merge; sync delta specs to `openspec/specs/`
