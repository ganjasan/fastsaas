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
- [x] 4.4 Wire into routers — `Depends(tenant_context)` applied to `GET /orgs/{slug}` and `DELETE /orgs/{slug}` in phase 5; further `/orgs/{slug}/...` endpoints in phases 6–8 reuse the same dependency.
- [x] 4.5 Tests — `tests/test_tenants_context.py` covers: unknown slug → None; member → `is_guest=False`; non-member → None (no info leak); guest with capability → `is_guest=True`; revoked capability ignored; soft-deleted org invisible.
- [x] 4.6 `db.py` — second engine `migrator_engine` (BYPASSRLS, small pool) + `migrator_session_scope()` for the bootstrap lookup. Disposed alongside the main engine.

## 5. Org service + endpoints

- [x] 5.1 `tenants/service.py::OrganisationService.create(name, slug, owner_actor_id)` — single TX: insert org + members row + mint `role:owner` capabilities. Migrator session (BYPASSRLS) so RLS-on-create works.
- [x] 5.2 `OrganisationService.list_for_actor(actor_id)` — joined SELECT through migrator session; soft-deleted orgs filtered.
- [x] 5.3 N/A — `get_by_slug` is supplied by `tenant_context` (returns `ctx.org`); endpoint just maps to schema.
- [x] 5.4 `OrganisationService.soft_delete(org_id, actor_id)` — sets `deleted_at`, mass-revokes `Capability` rows tagged `metadata.org_id = org_id`. Caller must check `can(admin, organisation, org_id)` first.
- [x] 5.5 `api/orgs.py` — `POST /orgs`, `GET /orgs`, `GET /orgs/{slug}`, `DELETE /orgs/{slug}`. Wired into `main.py`.
- [x] 5.6 Slug validation — `validate_slug()` raises `SlugError(code='org.slug_invalid'|'org.slug_reserved')`; route maps to HTTP 400. Duplicate slug → HTTP 409 `org.slug_taken` (DB UNIQUE + service-level pre-check).
- [x] 5.7 Tests — `tests/test_api_orgs.py` (12 integration tests, full pass): create happy path; invalid/reserved/duplicate slug; unverified-email gate; list returns only caller's orgs; empty-state for new user; non-member gets 404 (no leak); soft-deleted org disappears from get and list.
- [x] 5.8 `OrganisationService.list_projects(org_id)` helper landed for the future ProjectService hook (phase 7).

## 6. Membership service + endpoints

> Invitations live in their own table `org_invitations` (migration 0005),
> not in `magic_link_tokens`. The latter requires `actor_id NOT NULL`, but
> an invitee may not yet be an actor (pre-registration is the common case).
> Standard SaaS shape: own token hash, own TTL (7 days), own RLS isolation.

- [x] 6.1 `MembershipService.invite(org_id, email, role, invited_by)` — mints an `OrgInvitation` row with `sha256(token)` at rest; raw token returned only to the email task.
- [x] 6.2 `MembershipService.accept(raw_token, accepting_actor_id)` — atomic UPDATE...RETURNING that consumes the token, inserts the membership row, and mints the role bundle (`role:member` / `role:admin` / `role:viewer` / `role:compliance_officer`) for every existing project.
- [x] 6.3 `MembershipService.change_role(org_id, target_actor_id, new_role, actor_id)` — revoke old bundle + mint new in one transaction; refuses to demote the last OWNER.
- [x] 6.4 `MembershipService.remove(org_id, target_actor_id, actor_id)` — delete membership row + soft-revoke every Capability tagged with `metadata.org_id`; refuses to remove the last OWNER.
- [x] 6.5 `MembershipService.list_members` + `list_pending_invites` for the admin members page.
- [x] 6.6 `api/orgs.py` — `GET /orgs/{slug}/members`, `POST /orgs/{slug}/members/invite`, `POST /orgs/members/accept`, `PATCH /orgs/{slug}/members/{actor_id}`, `DELETE /orgs/{slug}/members/{actor_id}`. All wired through `tenant_context` + capability checks.
- [x] 6.7 Email template `org_invitation.{txt,html}.j2` + `email.send_org_invitation(to, raw, *, org_name, inviter_email)`.
- [x] 6.8 Migration 0005 — `org_invitations` table with role CHECK, indexes on `(org_id) WHERE consumed_at IS NULL`, RLS `tenant_isolation`, GRANT to `app_user`.
- [x] 6.9 Bundle fix: `role:owner` and `role:admin` now mint `read:organisation` explicitly. `can()` is a literal predicate, so admin no longer "implies" read; without the explicit row, owners would 403 on `GET /orgs/{slug}/members`.
- [x] 6.10 Tests — `tests/test_api_members.py` (9 integration): invite/accept happy path; invite as `owner` rejected; invite of existing member 409; accept with unknown / expired token 404; non-admin invite 403; change_role revokes old + mints new; last-owner protection on change_role + remove; remove revokes capabilities and the member loses visibility.

## 7. Project service + endpoints

- [x] 7.1 `ProjectService.create(org_id, name, slug, description, created_by)` — insert + fan-out: for every active member, mint capability rows for the `all_in_org` project templates of their primary bundle (operation × project × resource_id=new_project.id). One transaction.
- [x] 7.2 `ProjectService.list_in_org(org_id)` — `SELECT WHERE deleted_at IS NULL`, ordered by created_at.
- [x] 7.3 `ProjectService.get_by_slug(org_id, slug)` — single read.
- [x] 7.4 `ProjectService.update(project_id, name?, description?)` + `ProjectService.soft_delete(project_id, actor_id)` — capabilities are LEFT in place on soft-delete (restoration in Phase 2 backlog re-uses them; listing endpoints filter on `deleted_at IS NULL`).
- [x] 7.5 `api/projects.py` — `POST /orgs/{slug}/projects`, `GET`, `GET/{project_slug}`, `PATCH/{project_slug}`, `DELETE/{project_slug}`. Wired into `main.py`.
- [x] 7.6 Authorization at the route boundary:
   - `POST /projects`        → `can(admin, organisation, org.id)` (the project doesn't exist yet, so resource-scoped project caps cannot be checked); guests rejected.
   - `GET  /projects`        → members see all; guests see only those with an active `read:project` capability (UC-001 list-side enforcement).
   - `GET  /projects/{slug}` → `can(read, project, project.id)`; 404 on miss (no info leak between projects in the same org).
   - `PATCH /projects/{slug}` → `can(write, project, project.id)`.
   - `DELETE /projects/{slug}` → `can(admin, project, project.id)`.
- [x] 7.7 New `ProjectContext` + `project_context` dependency — resolves `{project_slug}` against the pinned org via the request's `app_user` session (RLS active), 404 on miss with `code = "project.not_found_or_forbidden"`.
- [x] 7.8 `mint_capability` extended to accept `bundle_name=` so project-create's fan-out tags new rows with the same primary bundle as the membership row, allowing future `revoke_bundle` calls to reach them.
- [x] 7.9 Tests — `tests/test_api_projects.py` (12 integration): owner create happy path; invalid/duplicate slug; member create 403; member sees all listed; unknown project 404; member updates 200, viewer 403; member delete 403, owner deletes → 204 → subsequent get 404 + list empty; **all_in_org propagation**: viewer joined before project exists still gets read access on a later-created project.

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
