# Tasks — theme-tokens-and-app-shell

Linked issue: ganjasan/fastsaas#5 (first half).

## 1. Token layer + presets

- [x] 1.1 `frontend/src/lib/theme.ts` — typed `ThemePreset` + `ThemeModeDefault` (re-exported from orval-generated `fastSaaS.schemas.ts`), `ThemeToken` const tuple, `ThemeVarMap` / `ThemePresetSpec` types, `PRESETS` map (5 presets × 2 modes × 20 tokens), `PRESET_LABELS`, `orgThemeSchema` Zod (strict), `parseOrgTheme` (defensive, never throws).
- [x] 1.2 `theme.css` already had the foundation (light + dark vars + `@theme inline`); kept as-is — `<ThemeProvider>` now overrides those vars at runtime per active preset, so the CSS-based defaults remain the unauthenticated fallback.
- [x] 1.3 `npm run build` clean — no Tailwind warnings.

## 2. ThemeProvider + hooks

- [x] 2.1 `frontend/src/features/theme/ThemeProvider.tsx` — reads org's preset + user's mode; resolves `system` via `matchMedia`; applies vars via `setProperty`; toggles `.dark` class; subscribes to OS dark-mode changes when mode is `system`; exposes `setPreviewPreset` for hover-preview.
- [x] 2.2 Mounted at root in `__root.tsx` inside `<QueryClientProvider>`.
- [x] 2.3 `frontend/src/features/theme/themeStore.ts` — Zustand + persist (key `fastsaas.theme`); `mode: ThemeModeDefault | null` where null means "inherit org default".

## 3. Backend endpoint

- [x] 3.1 `tenants/schemas.py` — `ThemePreset` + `ThemeModeDefault` StrEnums; `OrgThemeUpdateRequest` Pydantic (`extra="forbid"`).
- [x] 3.2 `OrganisationService.update_theme` — migrator session, before/after audit row, replaces (not merges) `organisations.theme`.
- [x] 3.3 `PATCH /orgs/{slug}/theme` route in `api/orgs.py`, gated on `Operation.ADMIN`. 403 `authz.forbidden` on miss; 404 if org missing/deleted.
- [x] 3.4 `make codegen` ran clean — orval emitted `ThemePreset`, `ThemeModeDefault`, `OrgThemeUpdateRequest` types and `useUpdateOrgThemeOrgsSlugThemePatch`/`updateOrgThemeOrgsSlugThemePatch` hook.

## 4. AppShell layout

- [x] 4.1 `routes/orgs/$slug.tsx` — TanStack file-based parent layout for `/orgs/$slug/*`. Pins slug into org store + renders `<AppShell>` with Outlet. (Used a parent file rather than a pathless `_app/` because the existing dot-flattened convention worked cleanly without a tree-wide rename.)
- [x] 4.2 `<AppShell>` — Sidebar + Topbar + main outlet. `bg-background text-foreground` so theme vars take effect.
- [x] 4.3 `<Sidebar>` — collapsible at `lg+` (16-rem ↔ 60-rem rail), `<Sheet>` drawer below `lg`, collapse persists in `localStorage` under `fastsaas.appShell.sidebarCollapsed`.
- [x] 4.4 `<ThemeModeToggle>` — Topbar dropdown (light/dark/system), icon reflects resolved mode.
- [x] 4.5 Existing dashboard children inherited the new layout without rename — TanStack's flat file naming routed `$slug.index.tsx`, `$slug.projects.*.tsx`, `$slug.settings.*.tsx` automatically under the new `$slug.tsx` parent.
- [x] 4.6 Stripped inline `<header>` + `<OrgSwitcher>` from `$slug.index.tsx`, `$slug.projects.index.tsx`, `$slug.projects.$projectSlug.tsx` (Topbar now owns the switcher; AppShell owns the `<main>` wrapper). Removed redundant `setSlug` calls now that the layout pins it once.

## 5. Settings layout + Branding panel

- [x] 5.1 `routes/orgs/$slug.settings.tsx` — vertical-tab layout via shadcn `<Tabs orientation="vertical">`. Active tab driven by URL match.
- [x] 5.2 `$slug.settings.members.tsx` rebased — stripped its `<main>` + inline header + redundant `setSlug`; now renders inside the Settings panel.
- [x] 5.3 `$slug.settings.branding.tsx` — fetches org via `useGetOrg`, hands `theme.preset` + `theme.mode_default` to `<ThemePicker>`.
- [x] 5.4 `<ThemePicker>` — preset radio cards (with mini swatches), `mode_default` Select, Save (`PATCH /orgs/{slug}/theme` via `useMutation`, invalidates `useGetOrg`), Cancel (reverts pending state + clears preview), hover/focus = preview, mouse-leave/blur = revert preview unless a different pending preset is active.
- [ ] 5.5 ~~useCan hook~~ — deferred. The ThemePicker is currently rendered for any org member who can reach `/settings/branding`; non-admins simply get 403 on Save. Capability gate at the route level is a separate UX-polish ticket (will land alongside `datatable-and-form-primitives` if scope allows).

## 6. Tests

- [x] 6.1 `lib/theme.test.ts` (15 tests) — preset map exhaustiveness across 5 presets × 2 modes × 20 tokens; Zod accepts each preset + rejects unknown + rejects extra keys; `parseOrgTheme` falls back gracefully.
- [x] 6.2 `features/theme/themeStore.test.ts` (3 tests) — null default, persists explicit choice, reset to null.
- [ ] 6.3 ~~ThemeProvider DOM smoke~~ — deferred. The provider's `setProperty` + `classList.toggle` calls hit `document.documentElement`; without a real DOM-test rig (jsdom + react-testing-library wiring with QueryClient mock) the test cost is disproportionate to what it protects. Covered indirectly by E2E (§6.7) when added.
- [x] 6.4 Backend integration — `test_owner_patches_theme_200_and_persists`: 200, body reflects, GET re-reads.
- [x] 6.5 Backend integration — `test_patch_theme_non_admin_403` (plain member) and `test_patch_theme_non_member_404` (outsider).
- [x] 6.6 Backend integration — `test_patch_theme_invalid_preset_422` and `test_patch_theme_unknown_field_422`.
- [ ] 6.7 ~~E2E (Playwright)~~ — deferred. A theme-picker click-through belongs to issue #7 (Playwright baseline) which will set up the dev-bypass login helper. Separate ticket.

## 7. Documentation

- [ ] 7.1 ~~Root `CLAUDE.md` recipe for "Add a Settings tab"~~ — deferred. Adds churn to a doc that isn't on the critical path; will fold into `datatable-and-form-primitives` once the second tab lands.
- [ ] 7.2 ~~`features/theme/CLAUDE.md` module guide~~ — deferred for the same reason; the in-file docstrings on `ThemeProvider`, `themeStore`, and `theme.ts` carry the contract for now.
- [ ] 7.3 ~~ADR-012 traces_to update~~ — will land in the archive PR (mirror of how prior changes added their slug to ADR-010 in their archive PR).

## 8. Validation + close-out

- [x] 8.1 `openspec validate theme-tokens-and-app-shell --strict` passes.
- [x] 8.2 `cd backend && uv run ruff check .` clean.
- [x] 8.3 `./run_test.sh -q` green — 221 passed (216 pre-existing + 5 new theme integration tests).
- [x] 8.4 `cd frontend && npm run build` clean (tsc + vite).
- [x] 8.5 `cd frontend && npm run lint` clean (biome).
- [x] 8.6 Frontend vitest — 50 passed (32 pre-existing + 18 new theme + themeStore tests).
- [ ] 8.7 **Manual UI smoke (cannot perform from this environment).** Reviewer should run `make dev`, log in, navigate to Settings → Branding, exercise: preset hover-preview, Save, light/dark toggle, sidebar collapse persistence, mobile-drawer behaviour at <`lg` viewport.
- [ ] 8.8 PR opened, linked to issue #5 (mention it's the first of two).
- [ ] 8.9 Archive change after merge; sync delta specs to `openspec/specs/design-system/spec.md` (new) + `openspec/specs/multi-tenancy/spec.md`.
