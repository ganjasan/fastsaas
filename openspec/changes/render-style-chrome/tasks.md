# Tasks — render-style-chrome

Linked issue: ganjasan/fastsaas#24.

## 1. Shell primitive

- [x] 1.1 New `frontend/src/components/layout/Shell.tsx` — render-prop slots (`sidebarHeader`, `sidebarSections`, `sidebarBottom`, `topbarLeft`, `topbarRight`, `children`). Hosts the lg-breakpoint Sheet drawer. Internal `ShellContext` exposes `collapsed` + `setDrawerOpen` to children that need them.
- [x] 1.2 `NavSection`/`NavItem` exports — `{ label?, items: { to, label, icon, exact? }[] }`.
- [x] 1.3 Active-state styling — `bg-primary/10 text-primary` for active, `bg-accent` for hover.
- [x] 1.4 Collapsed-rail support — `sidebarHeader` and `sidebarBottom` are render-props that receive `collapsed`; drawer renders with `collapsed=false` regardless.
- [x] 1.5 Sidebar collapse state moved into Shell (was inside Sidebar in #18) — same localStorage key `fastsaas.appShell.sidebarCollapsed`. `useSidebarDrawer()` hook exposes the drawer setter for mobile menu buttons.

## 2. WorkspaceSwitcher

- [x] 2.1 New `frontend/src/features/orgs/components/WorkspaceSwitcher.tsx` — compact card form: avatar tile (org initial on `--primary`) + name + chevron. Replaces `OrgSwitcher.tsx` (deleted).
- [x] 2.2 Collapsed form — when sidebar is collapsed, render avatar-only with `justify-center`; dropdown still opens on click.
- [x] 2.3 No remaining `OrgSwitcher` references in the tree.

## 3. Topbar refresh

- [x] 3.1 `<Topbar>` standalone file deleted; topbar lives inside `<Shell>` via `topbarLeft`/`topbarRight` slots.
- [x] 3.2 New `<Breadcrumb>` (`components/layout/Breadcrumb.tsx`) — single-segment, derives label from URL via `useRouterState`. Recognises Overview / Projects / Project / Settings / Members / Branding; returns null for unrecognised paths.
- [x] 3.3 New `<SearchTrigger>` — `Search` button with `⌘K` kbd hint; click handler is a TODO no-op for v1.
- [x] 3.4 New `<NewMenu>` — `+ New ⌄` dropdown with "Create project" (uses pinned org slug; navigates to `/orgs/{slug}/projects?new=1`) and "Create organisation" (links to `/orgs/new`). The `?new=1` search param opens the create dialog on mount in the Projects page.
- [x] 3.5 `<ThemeModeToggle>` from #18 carried over unchanged.
- [x] 3.6 New `<UserMenu>` (extracted from the old Topbar) — avatar trigger + email + Logout.

## 4. Sidebar bottom-chrome

- [x] 4.1 New `<SidebarBottomChrome>` — Status pill (green dot + "All systems operational"), Changelog button (placeholder TODO no-op), Help button (placeholder TODO no-op), Collapse toggle. Adapts to collapsed state (status text + button labels hide, Collapse stays).

## 5. AppShell refactor

- [x] 5.1 `<AppShell>` is now a thin wrapper around `<Shell>`. Supplies WorkspaceSwitcher header, two-item nav (Projects, Settings; Overview is the index), bottom chrome, breadcrumb topbar-left, search/new/theme/user topbar-right.
- [x] 5.2 `routes/orgs/$slug.tsx` parent layout untouched; mounts `<AppShell>` as before.
- [x] 5.3 Old `Sidebar.tsx` and `Topbar.tsx` deleted (now dead code).

## 6. Org overview redesign

- [x] 6.1 `routes/orgs/$slug.index.tsx` is now an Overview page — H1 "Overview" + supporting blurb.
- [x] 6.2 "Projects" subsection — grid of project cards (Link to detail, name + slug) plus a final dashed-bordered tile `+ Create new project`. Empty state collapses to just the dashed tile. (`description` field omitted because `ProjectListItem` from codegen doesn't carry it; project-detail page shows the description.)
- [x] 6.3 New `frontend/src/features/orgs/components/CreateProjectDialog.tsx` — extracted from the Projects page; both Overview and Projects import it. Accepts an optional `trigger` prop so callers compose their own button / dashed tile.
- [x] 6.4 Old quick-link cards (Projects / Members) removed — Sidebar nav covers their role.

## 7. Tests

- [x] 7.1 `Breadcrumb.test.tsx` — 8 cases: each known URL → label; unrecognised path renders nothing. Uses `vi.mock("@tanstack/react-router")` to feed pathname.
- [ ] 7.2 ~~Shell smoke + WorkspaceSwitcher unit~~ — deferred. Both depend on the QueryClient + ThemeProvider context to mount; the cost of the test rig outweighs what it verifies (mostly slot composition + className assertions). Visual smoke (manual) covers them.

## 8. Documentation

- [ ] 8.1 ~~`components/layout/CLAUDE.md` module guide~~ — deferred to the AdminShell PR (#19); it'll be the second consumer of `<Shell>` and the right time to write the guide is when both consumers exist.
- [ ] 8.2 ~~Root `CLAUDE.md` "Add a section to the Sidebar" snippet~~ — same reason; defer to #19.

## 9. Validation + close-out

- [x] 9.1 `openspec validate render-style-chrome --strict` passes.
- [x] 9.2 `cd backend && uv run ruff check .` clean (no backend changes; sanity check).
- [x] 9.3 `./run_test.sh -q` green — 221 passed (no backend changes).
- [x] 9.4 `cd frontend && npm run build && npm run lint && npm run test -- --run` clean — build OK, biome clean, 58 tests passed (50 pre-existing + 8 Breadcrumb).
- [ ] 9.5 PR opened, linked to issue #24.
- [ ] 9.6 **Manual UI smoke (cannot perform from this environment).** Reviewer should run `make dev`, log in, navigate to `/orgs/{slug}` and verify:
   - Workspace switcher in sidebar header (top-left), opens dropdown with org list + "Create new organisation".
   - Sidebar items use brand-coloured active state (filled `--primary/10` background + `--primary` text), distinct from the muted hover state.
   - Sidebar collapse toggle (bottom-right of sidebar) flips to icon-only at `lg+`; below `lg`, hamburger in topbar opens drawer.
   - Topbar shows breadcrumb on the left, Search trigger / `+ New` dropdown / theme toggle / user menu on the right.
   - Overview page renders project cards + dashed `+ Create new project` tile. Click tile → create dialog opens. Create succeeds → list refreshes.
   - Topbar `+ New ⌄ → Create project` navigates to `/orgs/{slug}/projects?new=1` and opens the dialog there.
   - Bottom chrome: green Status pill, Changelog, Help, Collapse.
- [ ] 9.7 Archive change after merge; sync delta specs to `openspec/specs/design-system/spec.md`.
