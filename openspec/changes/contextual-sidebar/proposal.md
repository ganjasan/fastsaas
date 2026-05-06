---
title: Contextual sidebar — Project context swaps the workspace nav for project-scoped items
status: in_progress
linked_issue: ganjasan/fastsaas (in-conversation request, no formal issue)
created: 2026-05-06
traces_to:
  adr:
    - "[[ADR-012_ui-shadcn-design-system-phased]]"
  use_cases: []
  stakeholders: []
---

## Why

The Render-style aesthetic locked in #24 ships one sidebar with workspace-level nav (Overview / Projects / Settings). When the user is inside a specific project (`/orgs/{slug}/projects/{projectSlug}/...`), the workspace nav stays visible — but the relevant actions are project-scoped (Project Overview, Sharing, future: Resources, Logs, Settings). Forcing the user to navigate "out of project → workspace nav → back into project" for every section is wrong.

This change swaps the sidebar nav based on URL context — Render's pattern. Workspace context keeps the existing nav. Project context replaces it entirely with project-scoped items + a "← Back to projects" header that exits the context.

## What changes

1. **Project page splits into a parent layout + subroutes**:
   - `routes/orgs/$slug.projects.$projectSlug.tsx` becomes a parent layout (project header + Outlet + 404-no-leak path + `useProjectContext`).
   - `routes/orgs/$slug.projects.$projectSlug.index.tsx` — Overview body (the existing "Coming soon" placeholder).
   - `routes/orgs/$slug.projects.$projectSlug.sharing.tsx` — Sharing body (`<ProjectSharing>` from #30).
2. **`useDashboardSections(slug)` hook** in `components/layout/dashboardNav.ts` returns workspace or project NavSection[] based on the active URL.
3. **AppShell consumes the hook** instead of a hardcoded constant. Same `<Shell>` primitive; only the sections change.
4. **Breadcrumb regex** extended for the new project subroutes (Overview matches `Project`, Sharing matches `Sharing`).
5. **Bug fix on `accept-share.$token.tsx`** — the existing useEffect mutation fired twice under React Strict Mode (vite dev), causing the second invocation to consume an already-consumed token and surface "Share expired". Gate via `useRef` so each token is accepted at most once per mount. Caught while smoke-testing the new contextual sidebar.

## What does NOT change

- The `<Shell>` primitive from #24. Still takes the same slot props; only the data flowing through `sidebarSections` differs by URL.
- AdminShell. Has its own static sections (#19); not affected.
- Backend. No API changes.

## Out of scope

- Project-level Settings / Resources / Logs subroutes — placeholder slots in the project sidebar today are limited to Overview + Sharing. New nav items added when those pages ship.
- Per-route customisation API (e.g. each route declares its sidebar via context provider). Today's URL-pattern matching covers all consumers; abstract to a context API when a third sidebar flavour appears.
- AdminShell consuming the same `useDashboardSections` hook — it has different concerns (cross-org structural items, no workspace switcher); separate static set works.
