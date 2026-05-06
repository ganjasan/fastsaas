# Tasks — platform-admin-foundation

Linked issue: ganjasan/fastsaas#19. Sibling issues #20–#23 plug into the shell built here.

## 1. Schema + ORM

- [x] 1.1 Migration `0008_actors_platform_staff.py` adds `is_platform_staff BOOLEAN NOT NULL DEFAULT FALSE` to `actors`.
- [x] 1.2 `Actor.is_platform_staff` field on the SQLModel ORM mirror.

## 2. Authz extension

- [x] 2.1 `Operation.PLATFORM_ADMIN = "platform_admin"` added to `authz/bundles.py`.
- [x] 2.2 `ResourceType.PLATFORM = "platform"` added to `authz/bundles.py`.
- [x] 2.3 `can()` short-circuit: when `resource_type == PLATFORM`, look up `actors.is_platform_staff` directly (via `_is_platform_staff` helper, pinned via the same `app.current_actor` GUC the capability self-read uses). Capabilities table is not consulted.
- [x] 2.4 `tests/test_authz_bundles.py::test_no_bundle_carries_platform_admin` — asserts no bundle template carries `Operation.PLATFORM_ADMIN`.

## 3. Backend admin module

- [x] 3.1 New package `backend/src/fastsaas/admin/`:
  - `__init__.py` — public exports
  - `schemas.py` — `AdminMeResponse(actor_id, email, display_name, is_platform_staff)`
  - `dependencies.py` — `require_platform_staff` FastAPI dep + `PlatformStaffDep` Annotated alias
- [x] 3.2 New router `backend/src/fastsaas/api/admin.py`:
  - `GET /admin/me` gated on `require_platform_staff`; returns the actor's identity + flag.
- [x] 3.3 `admin_router` wired into `main.py`.

## 4. Bootstrap CLI

- [x] 4.1 New script `backend/src/fastsaas/scripts/seed_platform_staff.py`:
  - argv: one email; non-zero exit on unknown email or orphan user row.
  - Updates `actors.is_platform_staff = TRUE` via migrator session; idempotent (no-op + 0 exit if already staff).
  - Writes one audit row (`entity_type="actor"`, `action="update"`, before/after diff). The script uses `set_audit_context(...)` with a synthetic intent_hash `req:seed-platform-staff` and the target actor as the audit actor (the bootstrap is by definition self-promoting).
- [x] 4.2 Makefile target `seed-platform-staff` — `USER_EMAIL=...` required, `make seed-platform-staff USER_EMAIL=alice@example.com`.

## 5. Frontend admin shell

- [x] 5.1 New route file `frontend/src/routes/admin.tsx` — parent layout:
  - Calls `useAdminMeAdminMeGet` (orval-generated from `/admin/me`).
  - On 401 → `useNavigate()` to `/auth/login`.
  - On 403 → `useNavigate()` to `/orgs`.
  - On 200 → renders `<AdminShell>` with the matched child route in the outlet.
- [x] 5.2 `<AdminShell>` component (`frontend/src/components/layout/AdminShell.tsx`) — wraps the `<Shell>` primitive from #24. Supplies a "PLATFORM ADMIN" pill (header), two-section UPPERCASE-labelled nav (`OPERATIONS`, `CONFIGURATION`), and a topbar with only Search + UserMenu (no workspace switcher, no `+ New ⌄`, no theme toggle — admin is cross-org and visually distinct). Bottom chrome (Status / Help / Changelog / Collapse) is the same primitive as AppShell.
- [x] 5.3 Six placeholder routes plus index redirect:
  - `routes/admin.index.tsx` — redirects to `/admin/orgs`
  - `routes/admin.orgs.tsx` — `<PlaceholderCard issueNumber={20}>`
  - `routes/admin.metrics.tsx` — `<PlaceholderCard issueNumber={20}>`
  - `routes/admin.health.tsx` — `<PlaceholderCard issueNumber={20}>`
  - `routes/admin.design-system.tsx` — `<PlaceholderCard issueNumber={23}>`
  - `routes/admin.auth.tsx` — `<PlaceholderCard issueNumber={21}>`
  - `routes/admin.oauth.tsx` — `<PlaceholderCard issueNumber={22}>`
- [x] 5.4 `make codegen` — `useAdminMeAdminMeGet` hook materialised in `frontend/src/api/generated/admin/admin.ts`.
- [x] 5.5 `<Breadcrumb>` regex extended for `/admin/*` paths.

(D6 from design.md — "fixed neutral theme on admin shell" — is best-effort in v1: the `<ThemeProvider>` from #5 still wraps the page tree, so a staff member who is also a member of a themed org sees their org's preset on the admin chrome. The "PLATFORM ADMIN" destructive-coloured pill provides the visual disambiguation. Full theme override is a follow-up; documented in the AdminShell file.)

## 6. Wiegers documentation

- [ ] 6.1 ~~ADR-019~~ — deferred. The structural-vs-bundle split is described in the change's design.md and in the `admin/__init__.py` docstring; promoting that material to a standalone ADR is the right move once the platform-admin epics #20–#23 land and demonstrate the model under load. Cross-referenced as `ADR-019 (TBD)` in code comments so the doc lands cleanly later.
- [ ] 6.2 ~~ADR-009 / ADR-013 traces_to update~~ — fold into the archive PR (matches the prior pattern: traces_to changes go in the archive commit for the change that needed them).

## 7. Documentation for Claude

- [ ] 7.1 ~~`backend/src/fastsaas/admin/CLAUDE.md` module guide~~ — the package-level docstring in `admin/__init__.py` covers the contract today (capability gate, structural authority, integration points for #20–#23). Promote to a CLAUDE.md when the second consumer (#20) lands and the patterns are proven.
- [ ] 7.2 ~~Root `CLAUDE.md` foundation-layer mention~~ — same reasoning. Update when the surface has real content beyond placeholders.

## 8. Tests

- [x] 8.1 `tests/test_authz_bundles.py::test_no_bundle_carries_platform_admin` — bundle catalogue does NOT reference `Operation.PLATFORM_ADMIN`.
- [x] 8.2 `tests/test_api_admin.py::test_seed_platform_staff_flips_flag_and_audits` — flag flips + one audit row appended; `test_seed_platform_staff_unknown_email_nonzero` — non-zero exit on missing user; `test_seed_platform_staff_already_staff_is_noop` — re-run is a no-op (no second audit row).
- [x] 8.3 `test_admin_me_unauthenticated_401` / `test_admin_me_non_staff_403` / `test_admin_me_staff_200`.
- [x] 8.4 `test_can_platform_admin_reflects_flag` — `can(PLATFORM_ADMIN, PLATFORM)` reflects the column for both pre- and post-promotion.
- [x] 8.5 Frontend Breadcrumb regex extended for `/admin/*` paths; 7 new test cases.

## 9. Validation + close-out

- [x] 9.1 `openspec validate platform-admin-foundation --strict` passes.
- [x] 9.2 `cd backend && uv run ruff check .` clean.
- [x] 9.3 `./run_test.sh -q` green — 229 passed (221 pre-existing + 8 new admin/bundle tests).
- [x] 9.4 `cd frontend && npm run build && npm run lint && npm run test -- --run` clean — build OK, biome clean, 65 tests passed (58 pre-existing + 7 admin breadcrumb).
- [ ] 9.5 PR opened, linked to issue #19; mentions sibling issues #20–#23 as the consumers.
- [ ] 9.6 Archive change after merge; sync delta specs to `openspec/specs/admin/spec.md` (new) + `openspec/specs/authorization/spec.md`.
