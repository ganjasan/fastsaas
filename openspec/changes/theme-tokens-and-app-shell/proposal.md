---
title: Theme tokens + AppShell + Settings layout — first half of #5 (themeable design system)
status: in_progress
linked_issue: ganjasan/fastsaas#5
created: 2026-05-05
traces_to:
  adr:
    - "[[ADR-004_frontend-stack]]"
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-011_frontend-project-layout]]"
    - "[[ADR-012_ui-shadcn-design-system-phased]]"
  use_cases: []
  stakeholders: []
---

## Why

Issue #5 covers the entire themeable design system epic. After review the scope is too large for a single PR (token formalisation + AppShell + Settings layout + DataTable + form primitives + theme picker = 30+ file change). The change is split into two; this is the first half. The second (`datatable-and-form-primitives`) follows after this lands.

The work this change ships closes the first DoD bullet of #5: **"Token override at the org level changes branding without component rewrites."** That requires a token layer, a way to persist an org-level theme choice, a way to surface it to the rendering tree, and the layout primitives that the surface lives inside (AppShell + Settings).

ADR-012 anchors the approach: shadcn/ui canonical, Tailwind v4 CSS-first tokens, **no Storybook in v1** (the issue body's "Storybook (or vitest-compose snapshots)" line predates ADR-012; this change documents the deviation in design.md). Phase 1 ships 3–5 pre-defined themes + simple `<ThemePicker>` in Settings; Phase 2 (full editor with sliders) is a separate epic.

## What changes

1. **Token layer formalisation** — extend `frontend/src/styles/theme.css` with spacing, typography, and elevation tokens; refactor existing colour vars into a typed Zod schema (`frontend/src/lib/theme.ts`) so presets are checked and the runtime override is type-safe.
2. **5 preset themes** per ADR-012: `default`, `modern`, `corporate`, `dark`, `high-contrast`. Each preset declares its CSS-var set; `<ThemeProvider>` at app root applies the active preset's vars to the document root via `style` attribute.
3. **`Organisation.theme` write API** — new `PATCH /orgs/{slug}/theme` endpoint, gated on `Operation.ADMIN` over `ResourceType.ORGANISATION`. Body: `{preset: PresetName, mode?: "light" | "dark" | "system"}`. Validates `preset` against the enum; persists to `organisations.theme` JSONB.
4. **Light/dark mode toggle** — per-user (localStorage-backed) `system | light | dark` choice. Stored in the existing `useOrgStore` peer (or a new `useThemeStore`). Applies the `.dark` class to `<html>` when resolved to dark.
5. **`<ThemeProvider>`** — top-level provider that reads `Organisation.theme` (server-side, per-org) and user mode pref (client-side, per-user) and computes the active CSS-var set + dark class.
6. **AppShell layout** — TanStack pathless route `/_app/orgs.tsx` hosting Sidebar + Topbar + main outlet, wraps every `/orgs/$slug/*` route. Sidebar collapsible, persists collapsed state in localStorage. Topbar: org switcher + user menu + theme-mode toggle.
7. **Settings layout** — `/_app/orgs/$slug/settings.tsx` pathless layout hosting vertical tabs (`Members`, `Branding`); current `$slug.settings.members.tsx` rebases under the layout. New `$slug.settings.branding.tsx` hosts the `<ThemePicker>`.
8. **`<ThemePicker>` component** — preset radio cards + light/dark/system mode selector. Save mutates `PATCH /orgs/{slug}/theme`. Live preview applies provisional vars while the dropdown is open.

## What does NOT change

- The schema. `organisations.theme` JSONB column has shipped since migration 0001; this change populates it.
- The component primitives. shadcn primitives stay copy-paste with no abstraction layer. Theming is purely CSS-var swap.
- Existing routes outside `/orgs/$slug/*`. `/login`, `/orgs` (list page), `/orgs/new` keep their bare layout — AppShell is per-org-shell, not app-global.
- Compliance officer / DPO read paths. Theme is org-owner concern.

## Out of scope (deferred to second change `datatable-and-form-primitives`)

- DataTable wrapper over TanStack Table.
- Form primitive helpers beyond what shadcn `form.tsx` already provides.
- Members page rewrite to use DataTable (it stays plain-table for this change).

## Out of scope (deferred to later epics)

- Per-org full theme editor with colour sliders / radius dial / font picker (Phase 2 from ADR-012).
- Public component catalogue (Phase 4 from ADR-012).
- Storybook (deferred per ADR-012 §"Storybook in v1 SaaS-core: NOT used"; reconsider when ≥20 custom non-shadcn components exist).
- Per-user "favourite preset" personalisation (theme is org-controlled in v1).
