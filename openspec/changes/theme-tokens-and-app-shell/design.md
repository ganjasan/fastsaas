## Context

`organisations.theme JSONB` has shipped since migration 0001 with a default of `'{}'::jsonb`. ADR-012 specifies the phased plan: Phase 1 ships pre-defined themes + simple picker; Phase 2 (separate epic) ships a full visual editor. This change is Phase 1.

shadcn/ui canonical theming is CSS-vars + Tailwind v4 `@theme inline` — already wired in `frontend/src/styles/theme.css`. The vars cover background / foreground / primary / secondary / muted / accent / destructive / border / input / ring / radius. What is missing is (a) the formal preset enum, (b) the runtime override mechanism, and (c) the persistence + API path. This change fills all three.

## Goals

- Owner can pick from 5 pre-defined presets (`default`, `modern`, `corporate`, `dark`, `high-contrast`) and the choice persists per-org via `PATCH /orgs/{slug}/theme`.
- Every component under the AppShell respects the active preset without component-level rewrites — pure CSS-var swap.
- Light/dark mode is a per-user preference orthogonal to the per-org preset.
- The dashboard has a coherent shell (Sidebar + Topbar) instead of ad-hoc `<main>` wrappers per route.
- The Settings page hosts the picker behind a vertical-tab layout that scales to additional admin panels.

## Non-goals

- Custom colour pickers / radius sliders. The Phase 2 epic owns that surface.
- Per-user "favourite preset" — theme is org-set in v1.
- Storybook. Per ADR-012 deferred.
- DataTable + form primitives — split into the follow-up change `datatable-and-form-primitives`.

## Decisions

### D1 — Spec areas: new `design-system` capability + delta to `multi-tenancy`

Frontend behaviour (theme application, layout shell, theme picker) lives in a new spec area `design-system`. The HTTP endpoint `PATCH /orgs/{slug}/theme` is a multi-tenancy concern (it mutates org settings), so it lands as a delta on the existing `multi-tenancy` spec.

**Rationale.** Spec areas group requirements by user-observable capability. The theme system is a distinct capability ("the app re-themes per org") and deserves its own spec; the API endpoint that persists the choice is an extension of the existing org-settings surface.

### D2 — Preset enum, not free-form theme JSONB

`organisations.theme` JSONB stores `{preset: "default" | "modern" | "corporate" | "dark" | "high-contrast", mode_default?: "light" | "dark" | "system"}`. Free-form `{primary: "#abc...", radius: "0.75rem", ...}` is rejected by the validator.

**Rationale.** Phase 1 is "pick from a curated list", not "design your own". The Phase 2 epic owns full customisation; until then, an unbounded theme JSONB invites three-week-old hot-pink dashboards we have to support. Constraining to an enum makes the API trivially validatable and the rollback safe (any preset rendering bug affects exactly the named preset).

The `mode_default` is the org's preferred default for new users — individual users can still toggle their own light/dark choice.

### D3 — Light/dark is per-user, not per-org

The user's chosen mode (`system` | `light` | `dark`) is stored in browser localStorage under `theme.mode`. Only the org-level `mode_default` lives in `organisations.theme`. On first load with no localStorage entry, the user inherits `mode_default`; from then on, their choice is sticky.

**Rationale.** Light/dark is an accessibility/preference dimension orthogonal to brand colour. Forcing org members onto a single mode loses accessibility flexibility; persisting per-user via localStorage is cheap and survives navigation but resets on a different browser/device — acceptable for v1.

### D4 — `<ThemeProvider>` writes CSS vars on `<html>`, not via stylesheet swap

The provider mounts at the app root inside `__root.tsx`. It reads:

- The currently-pinned org's `theme.preset` from the org store (filled by `useGetOrg` after `tenant_context` resolves).
- The user's `theme.mode` from localStorage (defaulting to `mode_default` of the active org if missing).

It computes the CSS-var set for the active preset and applies it via `document.documentElement.style.setProperty(...)` per var. The `.dark` class is toggled on `<html>` when the resolved mode is `dark` (or `system` and `prefers-color-scheme: dark`).

**Rationale.** Tailwind v4 `@theme inline` already maps the CSS vars to utility classes. Setting properties on `<html>` propagates instantly without HMR-style stylesheet swaps. No router-level CSS-in-JS is needed; this stays inside the existing CSS-vars idiom. Setting on `<html>` (not `<body>`) keeps the dark-mode media query and `prefers-color-scheme` plumbing simple.

### D5 — AppShell as a TanStack pathless layout, not a HOC

TanStack Router supports pathless layouts via `_layout.tsx` files. The shell lives at `frontend/src/routes/_app.tsx` (pathless — no URL segment) and wraps every nested route. `/orgs/$slug/*` becomes `/_app/orgs/$slug/*` in file system terms; URL is unchanged.

**Rationale.** Pathless layouts give us a single mount point for Sidebar + Topbar across the dashboard without prop-drilling. They preserve route-tree URL semantics. Wrapping at `__root.tsx` would force the AppShell on `/login` and `/orgs/new`, which are intentionally bare; pathless `_app` lets unauthenticated and pre-org pages opt out by living outside it.

### D6 — Sidebar collapse persists per-user; collapse triggers on `lg:` breakpoint

Collapsed/expanded state lives in localStorage under `appShell.sidebarCollapsed`. Below `lg` (1024px) the Sidebar transforms into a Sheet (slide-in drawer) — not a "collapsed icon-only" rail. The icon-only collapsed state is `lg`+ only.

**Rationale.** Three states (mobile drawer / lg collapsed rail / lg expanded) match the issue's "collapsible sidebar" without inventing a fourth. Drawer is shadcn's `sheet` primitive; collapsed rail toggles a Tailwind class.

### D7 — Settings vertical tabs use shadcn `tabs` with explicit orientation

shadcn `tabs.tsx` accepts an `orientation` prop forwarded from Radix. Vertical tabs render as a left-side rail with the panel on the right. The settings layout is `/_app/orgs/$slug/settings.tsx` hosting the tabs; the children are `members.tsx` (existing) and `branding.tsx` (new).

**Rationale.** Reusing the existing primitive avoids inventing a custom vertical-tab component. The orientation prop is a known Radix feature.

### D8 — `PATCH /orgs/{slug}/theme` ships in `api/orgs.py`, gated by `Operation.ADMIN`

Existing pattern: `DELETE /orgs/{slug}` is `can(actor, ADMIN, ORGANISATION, org.id)`. Theme write reuses the same gate — owners and admins can re-brand. Compliance officers cannot; DPOs cannot. The endpoint validates `preset` via a Pydantic enum and `mode_default` via a literal type.

**Rationale.** Re-using the existing gate avoids a fourth permission level. Branding is an admin concern.

### D9 — `<ThemePicker>` does live preview on hover, persists on confirm

The picker shows preset radio cards. Hovering / focusing a card applies its vars provisionally to the document root (so the user sees the preview live). Selection is committed only when the user clicks "Save". Cancel reverts to the last persisted preset.

**Rationale.** Live preview is the entire point of a theme picker; otherwise users save-and-rollback through trial and error. Provisional application via `<ThemeProvider>`'s setter API keeps the change cheap (CSS-var setProperty calls).

### D10 — No Storybook (per ADR-012)

The issue body lists "Storybook (or vitest-compose snapshots)". ADR-012 explicitly defers Storybook to Phase 3+. This change documents the deviation here and skips both Storybook and snapshot scaffolding. Verification is via:

- `npm run build` — type-checks the entire frontend tree.
- `npm run lint` — biome.
- Existing vitest unit tests for any non-trivial component logic.
- Eyeball-in-dev — `npm run dev` + manual visual sweep.

If a future change adds ≥20 custom (non-shadcn) components, ADR-012 Phase 3 fires and Storybook is reconsidered then.

## Risks / trade-offs

- **Preset rendering bugs land per-tenant.** A bug in the `corporate` preset's vars shows up for every org that picked it, atomically. Mitigation: the preset enum is small and the vars are flat; visual review of all 5 presets in the PR.
- **localStorage drift on multi-device usage.** A user logging in from a different browser sees the org's `mode_default`, not their previous choice. Acceptable; documented in §D3.
- **Pathless `_app` layout requires route-tree regeneration.** TanStack Router's `routeTree.gen.ts` rebuilds on any new route file. CI-side: nothing to do; locally, `npm run dev` regenerates on save.
- **AppShell wraps the existing org-overview-page**, which currently does its own `<header>` with `<OrgSwitcher>`. The org-switcher logic moves into the Topbar; the page loses its inline header. Mitigated by direct review.
- **Live-preview revert on cancel** must restore the last-persisted preset, not the on-mount default. State management lives inside `<ThemePicker>`; the provider exposes a `setPreviewPreset` setter that the picker calls.

## Migration plan

- No DB migration. `organisations.theme` already exists and defaults to `{}`. On first read, an empty theme resolves to `default` preset + `system` mode.
- Existing orgs (created before this change) gain themeability automatically — first time an admin opens Settings → Branding, they see all five preset cards with `default` selected.
- Frontend route-tree regenerates on save; no manual `routeTree.gen.ts` editing.

## Open questions

- **Q: Should `mode_default = "system"` be the implicit default when `theme.mode_default` is absent, vs an explicit value persisted on org create?** Tentatively: implicit `system` on read; do not write a row-default on create. Avoids touching `OrganisationService.create`. Re-open if the API contract feels too lossy.
- **Q: Does "system" mode listen for `prefers-color-scheme` changes live, or is it resolved once at mount?** Tentatively: live via `matchMedia(...)`. The provider subscribes; toggling OS dark-mode flips the dashboard without a reload. Cheap.
- **Q: ThemePicker preview on touch devices** — hover/focus doesn't translate cleanly. v1 falls back to "tap = preview, tap again = save" which is awkward. Acceptable for desktop-first v1; revisit when mobile UX is priority.

## References

- Issue ganjasan/fastsaas#5.
- ADR-004 (frontend stack: React + Vite + Radix + Tailwind v4 + CVA).
- ADR-011 (frontend project layout).
- ADR-012 (shadcn/ui canonical + phased design-system rollout).
- Existing `frontend/src/styles/theme.css` (CSS-var foundation already in place).
- shadcn registry: https://ui.shadcn.com/.
