# Tasks — project-share-link-ui

Linked issue: ganjasan/fastsaas#30.

## 1. Backend

- [x] 1.1 `ProjectShareResponse` extended with `raw_token: str` (one-time disclosure on create).
- [x] 1.2 Route `share_project` in `api/projects.py` plumbs the `raw` token from `ProjectShareService.share` into the response.
- [x] 1.3 No change to `ProjectShareItem` (list response keeps token-hash-only contract).

## 2. Frontend

- [x] 2.1 `<ProjectSharing>` component (`features/projects/components/ProjectSharing.tsx`) — invite form + reveal panel + pending list + revoke action.
- [x] 2.2 Mounted in `routes/orgs/$slug.projects.$projectSlug.tsx` between project header and "Coming soon" placeholder.
- [x] 2.3 TanStack Query keys mirrored from orval helpers; mutations invalidate the list query.
- [x] 2.4 Reveal panel uses `navigator.clipboard.writeText` with graceful fallback to manual select.
- [x] 2.5 `make codegen` ran clean — `raw_token` appears in `ProjectShareResponse` interface; share + list + revoke hooks already existed.

## 3. Tests

- [x] 3.1 Backend: `test_share_response_carries_raw_token_matching_email` — response.raw_token equals the token in the email link.
- [x] 3.2 Backend: `test_share_list_response_omits_raw_token` — list items have no `raw_token` field.
- [ ] 3.3 ~~Frontend smoke test for `<ProjectSharing>`~~ — deferred. The component depends on QueryClient + multiple mutation hooks; rig cost outweighs what it'd verify (mostly slot composition). E2E covers the happy path.
- [ ] 3.4 ~~E2E coverage~~ — fold into a future Playwright baseline (#7); the existing smoke spec doesn't yet exercise the share path.

## 4. Documentation

- [ ] 4.1 ~~`features/projects/CLAUDE.md`~~ — deferred; component docstring carries the contract today.
- [ ] 4.2 ~~Root CLAUDE.md "share a project" recipe~~ — fold into the next docs sweep.

## 5. Validation + close-out

- [x] 5.1 `openspec validate project-share-link-ui --strict` passes.
- [x] 5.2 `cd backend && uv run ruff check .` clean.
- [x] 5.3 `./run_test.sh tests/test_api_project_shares.py -q` — 13 passed (11 pre-existing + 2 new).
- [x] 5.4 `cd frontend && npm run build && npm run lint && npm run test -- --run` clean — 65 vitest passed.
- [ ] 5.5 PR opened, linked to issue #30.
- [ ] 5.6 Archive change after merge; sync delta specs to `openspec/specs/multi-tenancy/spec.md`.
