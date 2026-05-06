# Tasks — contextual-sidebar

In-conversation request from operator (no formal issue). Cross-refs #24 (Render-style chrome) + #30 (Project share-link UI).

## 1. Project page split

- [x] 1.1 `routes/orgs/$slug.projects.$projectSlug.tsx` becomes a parent layout — project fetch + 404-no-leak + `useProjectContext` provider + project header + `<Outlet>`.
- [x] 1.2 `routes/orgs/$slug.projects.$projectSlug.index.tsx` — Overview body (placeholder card).
- [x] 1.3 `routes/orgs/$slug.projects.$projectSlug.sharing.tsx` — Sharing body (renders `<ProjectSharing>`).

## 2. Contextual sidebar

- [x] 2.1 `components/layout/dashboardNav.ts` — `useDashboardSections(workspaceSlug)` reads URL via `useRouterState`, returns project sections when the URL matches `/orgs/{slug}/projects/{projectSlug}(/...)`, else workspace sections.
- [x] 2.2 AppShell consumes the hook instead of a hardcoded constant.
- [x] 2.3 Breadcrumb regex extended for `/projects/{slug}/sharing` route.

## 3. Strict-mode bug fix on accept-share

- [x] 3.1 `routes/orgs/accept-share.$token.tsx` — gate the accept mutation with a `useRef` keyed on the token so React Strict Mode's double-effect doesn't consume the token twice.

## 4. Tests

- [x] 4.1 `Breadcrumb.test.tsx` — added `/orgs/acme/projects/q4/sharing → Sharing` case.
- [ ] 4.2 ~~Unit tests for `useDashboardSections`~~ — deferred. The hook is a tiny URL-regex switch; visual smoke covers it. Add when the third context flavour appears (e.g. AdminShell consuming the same hook).

## 5. Validation + close-out

- [x] 5.1 `openspec validate contextual-sidebar --strict` passes.
- [x] 5.2 `cd backend && uv run ruff check .` clean (no backend changes).
- [x] 5.3 `cd frontend && npm run build && npm run lint && npm run test -- --run` clean — 66 vitest passed (65 + 1 new Breadcrumb case).
- [x] 5.4 **Playwright smoke verified**: workspace context renders Overview / Projects / Settings; navigating to `/orgs/acme/projects/alpha` swaps the sidebar to `← Back to projects` + ALPHA label + Overview/Sharing; clicking Sharing navigates to `/sharing` with the active highlight; Back-to-projects swaps the sidebar back.
- [ ] 5.5 PR opened.
- [ ] 5.6 Archive change after merge; sync delta specs to `openspec/specs/design-system/spec.md`.
