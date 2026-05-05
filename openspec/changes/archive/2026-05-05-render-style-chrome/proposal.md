---
title: Render-style dashboard chrome — workspace switcher in sidebar, breadcrumb topbar, Overview cards
status: in_progress
linked_issue: ganjasan/fastsaas#24
created: 2026-05-05
traces_to:
  adr:
    - "[[ADR-011_frontend-project-layout]]"
    - "[[ADR-012_ui-shadcn-design-system-phased]]"
  use_cases: []
  stakeholders: []
---

## Why

The AppShell shipped in #18 is a basic shadcn-style chrome (Sidebar with a few nav items, Topbar with the OrgSwitcher and theme toggle, page-level content). Functional but visually generic. The operator wants every FastSaaS-built surface to follow a Render-like aesthetic — workspace switcher in the sidebar header, UPPERCASE section labels for nav groups, breadcrumb-style topbar, Overview pages composed of cards (including a dashed-border "+ Create new" tile).

This change locks the visual contract as a reusable `<Shell>` primitive and restyles the existing AppShell + Settings + Overview to consume it. The follow-up issue #19 (Platform admin foundation) consumes the same primitive for `<AdminShell>` — so the chrome ships once, gets reused twice.

## What changes

1. **New `<Shell>` primitive** (`frontend/src/components/layout/Shell.tsx`) parameterised by:
   - `sidebarHeader: ReactNode` — workspace switcher (org dashboard) or "PLATFORM ADMIN" label (admin shell).
   - `sidebarSections: NavSection[]` where `NavSection = { label?: string; items: NavItem[] }` — UPPERCASE label rendered when present, plain list when absent.
   - `sidebarBottom: ReactNode` — defaults to Status pill + Help + Changelog + Collapse, but caller can override.
   - `topbarLeft: ReactNode` — breadcrumb / current section.
   - `topbarRight: ReactNode` — composed by caller (Search trigger, +New dropdown, user menu).
   - `children` — main content.
2. **`<AppShell>` refactor** — becomes a thin wrapper around `<Shell>`. Supplies a compact `<WorkspaceSwitcher>` in the sidebar header, current Projects + Settings as the (single, label-less) nav section, and a topbar with breadcrumb + Search trigger + `+ New` dropdown + user menu.
3. **`<WorkspaceSwitcher>` (renamed/redesigned `<OrgSwitcher>`)** — compact workspace card form: avatar tile + name + chevron, opens a dropdown with org list + "Create new organisation". Lives in the sidebar header, not the topbar.
4. **`<StatusPill>` / `<ChangelogLink>` / `<HelpLink>`** — the bottom chrome components. Status is static "All systems operational" until issue #20's Health page lands and we wire to `/api/admin/health`. Help and Changelog link to placeholder routes (or `#`, which is the v1 reality).
5. **`<NewMenu>`** — `+ New ⌄` dropdown in the topbar with "Create project" (current org) and "Create organisation" actions.
6. **`<SearchTrigger>`** — button with `⌘K` shortcut hint. v1 is a placeholder no-op (TODO comment + console.log); the real command palette is its own epic.
7. **Overview redesign** — `/orgs/{slug}` becomes an Overview page: H1 "Overview" + right-aligned `+ New ⌄`, then a "Projects" subsection rendering project cards (name, slug, description) plus a dashed-border tile `+ Create new project` as the last item. The current quick-link cards (Projects / Members) are removed — Sidebar nav covers their role.
8. **Active-state polish** — active nav item uses `bg-primary/10` + `text-primary` (was `bg-accent text-accent-foreground` — neutral grey, doesn't read as "active brand"). Hover stays on `bg-accent`.

## What does NOT change

- The token map / preset list / `<ThemeProvider>` / `<ThemePicker>` / `useThemeStore` from #18. All carry forward unchanged.
- The `PATCH /orgs/{slug}/theme` endpoint and its tests from #18.
- The Settings vertical-tab layout (`/orgs/{slug}/settings`) — Members + Branding tabs stay. Only the surrounding chrome changes.
- TanStack Router file-tree convention. New components plug into existing routes; no route renames.

## Out of scope

- Functional command palette (`⌘K`) — search trigger is a no-op placeholder.
- Functional notification / changelog feeds — links go to `#` for now.
- Real status check (Status pill is static until #20).
- AdminShell composition — that's #19's PR; this PR ships only the primitive `<Shell>` it will consume.
- DataTable + form primitives — second half of #5 (separate change).
