# Tasks — platform-admin-foundation

Linked issue: ganjasan/fastsaas#19. Sibling issues #20–#23 plug into the shell built here.

## 1. Schema + ORM

- [ ] 1.1 Migration `0008_actors_platform_staff.py` adds `is_platform_staff BOOLEAN NOT NULL DEFAULT FALSE` to `actors`.
- [ ] 1.2 `Actor.is_platform_staff` field on the SQLModel ORM mirror.

## 2. Authz extension

- [ ] 2.1 `Operation.PLATFORM_ADMIN = "platform_admin"` in `authz/bundles.py`.
- [ ] 2.2 `ResourceType.PLATFORM = "platform"` in `authz/bundles.py`.
- [ ] 2.3 `can()` short-circuit: if `resource_type == PLATFORM`, look up `actors.is_platform_staff` directly via the migrator session (no capability rows). Cache miss for non-staff is fine — flag-flip is rare.
- [ ] 2.4 `tests/test_authz_bundles.py`: assert no bundle template carries `Operation.PLATFORM_ADMIN`.

## 3. Backend admin module

- [ ] 3.1 Create `backend/src/fastsaas/admin/` package:
  - `__init__.py`
  - `schemas.py` — `AdminMeResponse(actor_id, email, display_name, is_platform_staff: bool)`.
  - `dependencies.py` — `require_platform_staff` FastAPI dep, raises 403 `authz.forbidden` if `can(actor, PLATFORM_ADMIN, PLATFORM)` is False.
- [ ] 3.2 New router `backend/src/fastsaas/api/admin.py`:
  - `GET /admin/me` returning the actor + flag (gated on `require_platform_staff`).
- [ ] 3.3 Wire `admin_router` into `main.py`.

## 4. Bootstrap CLI

- [ ] 4.1 New script `backend/src/fastsaas/scripts/seed_platform_staff.py`:
  - argv: one email
  - Looks up `User.email -> User.actor_id`. Errors out non-zero on miss.
  - Updates `actors.is_platform_staff = TRUE` via migrator session.
  - Records an audit row (`entity_type="actor"`, `action="update"`, `diff` showing the flip). Uses `set_audit_context(...)` to inject a SERVICE actor for the script run (or HUMAN with the operator as the actor — TBD; default to a synthetic SERVICE actor named `platform-bootstrap`).
- [ ] 4.2 Makefile target `seed-platform-staff` invoking the script with `USER_EMAIL=`.

## 5. Frontend admin shell

- [ ] 5.1 New route file `frontend/src/routes/admin.tsx` — pathless / parent layout:
  - Calls `useAdminMe` (`/api/admin/me`).
  - On 401 → `useNavigate()` to `/auth/login`.
  - On 403 → `useNavigate()` to `/orgs`.
  - On 200 → renders `<AdminShell>` with the Outlet.
- [ ] 5.2 `<AdminShell>` component (`frontend/src/components/layout/AdminShell.tsx`):
  - Sidebar with six items: `Orgs`, `Metrics`, `Health`, `Design system`, `Auth`, `OAuth providers`. Includes a sticky "PLATFORM ADMIN" pill at the top.
  - Topbar with the staff actor's email + a Logout action.
  - Hard-coded neutral theme (does not consume `<ThemeProvider>` from #5; uses the `default` preset inline).
- [ ] 5.3 Six placeholder routes:
  - `routes/admin.orgs.tsx` — placeholder card "Coming soon — see #20".
  - `routes/admin.metrics.tsx` — "Coming soon — see #20".
  - `routes/admin.health.tsx` — "Coming soon — see #20".
  - `routes/admin.design-system.tsx` — "Coming soon — see #23".
  - `routes/admin.auth.tsx` — "Coming soon — see #21".
  - `routes/admin.oauth.tsx` — "Coming soon — see #22".
  - `routes/admin.index.tsx` — redirect / link to `/admin/orgs`.
- [ ] 5.4 Run `make codegen` so `useAdminMe` (orval-generated hook) appears.

## 6. Wiegers documentation

- [ ] 6.1 New ADR-019 — "Platform staff actor model": structural-vs-bundle split, why the flag (not a cross-org bundle), how to bootstrap, how subsequent epics plug in.
- [ ] 6.2 Update ADR-009 traces_to to reference this change + ADR-019.
- [ ] 6.3 Update ADR-013 traces_to to reference this change (the new `Operation.PLATFORM_ADMIN` extends the operation enum).

## 7. Documentation for Claude

- [ ] 7.1 New `backend/src/fastsaas/admin/CLAUDE.md` — module guide for downstream epics #20–#23: where their endpoints live, capability gate (`require_platform_staff`), shell route convention.
- [ ] 7.2 Update root `CLAUDE.md` "What FastSaaS is" — add a fourth foundation layer ("Platform admin — staff flag + admin shell + 6 surfaces in flight").

## 8. Tests

- [ ] 8.1 Unit — `Operation.PLATFORM_ADMIN` exists; bundle catalogue does NOT reference it (extends `tests/test_authz_bundles.py`).
- [ ] 8.2 Backend integration — `seed_platform_staff` script flips a user's flag + writes the audit row.
- [ ] 8.3 Backend integration — `GET /admin/me` returns 200 for staff, 403 for non-staff, 401 for unauthenticated.
- [ ] 8.4 Backend integration — `can(actor, PLATFORM_ADMIN, PLATFORM)` reflects the flag.
- [ ] 8.5 Frontend unit — placeholder text on each `admin.*.tsx` route mentions the right follow-up issue number.

## 9. Validation + close-out

- [ ] 9.1 `openspec validate platform-admin-foundation --strict` passes.
- [ ] 9.2 `cd backend && uv run ruff check .` clean.
- [ ] 9.3 `./run_test.sh -q` green.
- [ ] 9.4 `cd frontend && npm run build && npm run lint && npm run test -- --run` clean.
- [ ] 9.5 PR opened, linked to issue #19; mentions sibling issues #20–#23 as the consumers.
- [ ] 9.6 Archive change after merge; sync delta specs to `openspec/specs/admin/spec.md` (new) + `openspec/specs/authorization/spec.md`.
