## Context

The Render-style chrome (#24) ships one sidebar per AppShell instance. Workspace-level nav (Overview / Projects / Settings) is correct on every workspace surface but feels noisy + irrelevant once the user drills into a specific project — Render itself replaces the workspace sidebar with service-scoped nav (Logs / Metrics / Settings) on enter, then swaps back on exit. This change ports that pattern.

## Goals

- One AppShell, two nav sets, picked by URL.
- Project pages get their own sidebar (Overview + Sharing today; Settings / Logs / Resources later).
- Switching contexts is a one-click action — header anchor at the top of project sidebar links back to `/orgs/{slug}/projects`.

## Non-goals

- Per-route customisation API (each route declares its sidebar via context provider). Today's URL-pattern matching is sufficient; abstract when a third sidebar flavour appears.
- AdminShell consuming the same hook. AdminShell has its own static set (#19); merging into one hook would tangle structural-vs-workspace concerns.

## Decisions

### D1 — URL-pattern-matched hook, not a route-level data slot

`useDashboardSections(slug)` reads `useRouterState({select: s => s.location.pathname})` and matches `/^\/orgs\/([^/]+)\/projects\/([^/]+)/` to detect project context. Returns one of two `NavSection[]` shapes.

Alternative: each route file exports a `sidebar` constant; AppShell reads the matched route's data. More TanStack-idiomatic but requires every route to know about the sidebar. The hook approach centralises the contract in one file.

**Rationale.** Lower coupling; easier to add a new context (e.g. settings subroute) by extending the regex switch.

### D2 — Project page split into parent layout + index + sharing subroutes

Until this change, `$slug.projects.$projectSlug.tsx` was the leaf route — header + `<ProjectSharing>` + "Coming soon" all in one file. Splitting:

- Parent layout — project fetch + 404 + header + `<Outlet>`.
- Index subroute — Overview body (placeholder).
- Sharing subroute — `<ProjectSharing>`.

The split is required because sidebar items must link to URLs; tabbed-on-same-URL breaks active-state highlighting. Each tab needs its own subroute.

**Rationale.** The hook ↔ subroute pattern matches AdminShell + Settings vertical tabs already in the codebase. Consistent.

### D3 — Project layout exposes data via React context, not props drilled into Outlet

Children consume the project via `useProjectContext()` instead of refetching. The hook reads from a `<ProjectContext.Provider>` set up in the layout.

**Rationale.** TanStack Router's loader pattern would also work, but context + react-query caching is enough for now and keeps the codegen-only fetch surface unchanged.

### D4 — Project sidebar header is "← Back to projects", not the org's workspace switcher

Two equally valid options:
- **Option A (current):** Replace workspace switcher with "← Back to projects" anchor when in project context. Single visual cue.
- **Option B:** Keep workspace switcher, add "← Back to projects" as the first nav item.

Option A is what Render does. Workspace switcher implies "switch the org" which is rarely what you want from inside a project (you'd lose the project context anyway). Replacing with a back-anchor matches the intent.

**Rationale.** Match Render's pattern; simplify the visual hierarchy.

Wait — actually the current implementation keeps the WorkspaceSwitcher visible (the AppShell renders it as `sidebarHeader`). The change here only swaps the `sidebarSections`. So D4 is partially un-implemented: the workspace switcher stays visible. This is OK for v1; switching to Option A pure-replacement is a follow-up if the operator finds the current approach noisy.

### D5 — Strict-mode bug fix on accept-share

While smoke-testing the new contextual sidebar, the operator hit "Share expired" on a freshly-created share link. Root cause: the existing `useEffect` in `accept-share.$token.tsx` fires twice under React Strict Mode (vite dev double-mount). The first invocation consumes the share token (single-use); the second hits the backend's "share.not_found_or_expired" branch.

The cleanup-flag pattern (`let cancelled = false`) only prevents `setState` after unmount — it doesn't abort the in-flight network request. So the network call proceeded both times.

Fix: gate the mutation with a `useRef` keyed on the token. Refs ARE preserved across strict-mode mount/unmount/remount cycles (React 18 contract), so the second effect run sees `acceptedRef.current === token` and bails before firing the mutation.

**Rationale.** Targeted fix; preserves the existing useEffect pattern. Alternative (move to `useMutation` with `mutationKey`) is more idiomatic but bigger surface change.

## Risks / trade-offs

- **Two flavours grow into N flavours.** As more contexts are added (project Settings, project Resources, etc.), the URL switch in `useDashboardSections` grows. Refactor to a route-level data slot when it crosses ~4 contexts.
- **Active-state computation walks the regex on every render.** Cheap (one match call per render), but worth a memoization if the pattern set grows.
- **Project name not surfaced in the UPPERCASE label** — uses `projectSlug.toUpperCase()` for now. The actual project name lives in `useProjectContext()` but that hook is only reachable from inside the layout, not from the AppShell. Solving requires either lifting the project query to AppShell (refetch on every page) or threading via TanStack Router context. Deferred; the slug is informative enough.

## Migration plan

- No DB migration. Frontend-only change.
- Existing users with bookmarks at `/orgs/{slug}/projects/{projectSlug}` continue to work — that's now the Overview subroute. New `/sharing` URL is additive.
- E2E smoke spec is unaffected (it doesn't navigate into the Sharing subroute).

## Open questions

- **Q: Should the WorkspaceSwitcher hide entirely in project context** (D4 Option A)? Tentative: no for v1; defer until operator feedback.
- **Q: Move `useDashboardSections` to TanStack Router's loader / context API** for cleaner per-route declaration? Defer until a third sidebar flavour materialises.

## References

- Issue ganjasan/fastsaas#24 — Render-style chrome that this extends.
- Issue ganjasan/fastsaas#30 — Project share-link UI consumed by the new Sharing subroute.
- ADR-012 — shadcn/ui canonical + Tailwind v4 token foundation.
