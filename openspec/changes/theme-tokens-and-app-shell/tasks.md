# Tasks — theme-tokens-and-app-shell

Linked issue: ganjasan/fastsaas#5 (first half).

## 1. Token layer + presets

- [ ] 1.1 Add a typed preset module `frontend/src/lib/theme.ts`:
  - `PresetName = "default" | "modern" | "corporate" | "dark" | "high-contrast"`
  - `ModeDefault = "light" | "dark" | "system"`
  - `OrgTheme = { preset: PresetName; mode_default?: ModeDefault }` Zod schema (the schema mirrors the body of `PATCH /orgs/{slug}/theme`).
  - `PRESETS: Record<PresetName, ThemeVarMap>` — each entry declares the full var set covering all 20 keys from the design-system spec.
- [ ] 1.2 Re-organise `frontend/src/styles/theme.css` so the `:root` block ships only the `default` preset's vars (keeps it as the static-CSS fallback for unauthenticated routes); presets 2–5 live in JS only and apply via `<ThemeProvider>`.
- [ ] 1.3 Verify `npm run build` produces no Tailwind warnings about missing CSS vars.

## 2. ThemeProvider + hooks

- [ ] 2.1 `frontend/src/features/theme/ThemeProvider.tsx`:
  - Reads the active org's `theme.preset` from `useOrgStore` (or a new derived selector).
  - Reads the user's `theme.mode` from a new `useThemeStore` (Zustand, localStorage-persisted).
  - Computes the active preset's var set + dark-class flag; applies via `document.documentElement.style.setProperty(...)` and `classList.toggle("dark", ...)`.
  - Subscribes to `matchMedia("(prefers-color-scheme: dark)")` when mode is `system`.
  - Exposes `useThemeContext()` with `setPreviewPreset(preset | null)` (used by `<ThemePicker>` for hover-preview); `null` reverts to the persisted preset.
- [ ] 2.2 Mount `<ThemeProvider>` at the top of `__root.tsx`, inside `<QueryClientProvider>` (it depends on the query cache for org reads).
- [ ] 2.3 `useThemeStore` — Zustand store with `mode: "light" | "dark" | "system"`, persisted to `localStorage` under key `theme.mode`.

## 3. Backend endpoint

- [ ] 3.1 Pydantic enum + body schema in `backend/src/fastsaas/tenants/schemas.py`:
  - `class ThemePreset(StrEnum)` with the five values
  - `class ThemeModeDefault(StrEnum)` with `light/dark/system`
  - `class OrgThemeUpdateRequest(BaseModel)` with `preset: ThemePreset`, `mode_default: ThemeModeDefault | None = None`, `model_config = ConfigDict(extra="forbid")`
- [ ] 3.2 `OrganisationService.update_theme` in `backend/src/fastsaas/tenants/service.py`:
  - Loads the org via migrator session.
  - Records before/after theme via `audit.record(action="update", entity_type="organisation", ...)` with the diff.
  - Replaces (not merges) `organisations.theme` JSONB.
  - Returns the updated `Organisation`.
- [ ] 3.3 Route `PATCH /orgs/{slug}/theme` in `backend/src/fastsaas/api/orgs.py`:
  - `TenantContextDep` resolves the slug.
  - `await can(actor, Operation.ADMIN, ResourceType.ORGANISATION, ctx.org.id, db, redis)` — 403 `authz.forbidden` on miss.
  - Delegates to `OrganisationService.update_theme`.
  - Returns the updated `OrgRead`.
- [ ] 3.4 Run `make codegen` so the new endpoint + types appear in `frontend/src/api/generated/`.

## 4. AppShell layout

- [ ] 4.1 Create `frontend/src/routes/_app.tsx` (TanStack pathless layout):
  - Renders `<AppShell>` from `frontend/src/components/layout/AppShell.tsx`.
  - Outlet for nested routes.
- [ ] 4.2 `<AppShell>` component:
  - `<Sidebar>` (left, collapsible) with nav items: Overview, Projects, Settings.
  - `<Topbar>` (top): `<OrgSwitcher>` (existing), user menu (logout), `<ThemeModeToggle>`.
  - Main outlet container with proper padding + max-width.
- [ ] 4.3 `<Sidebar>` collapse:
  - Persists to `localStorage` under `appShell.sidebarCollapsed` (boolean).
  - At viewport <`lg`, renders as `<Sheet>` (shadcn drawer) with a hamburger trigger in the Topbar.
- [ ] 4.4 `<ThemeModeToggle>`: dropdown (light/dark/system) reading + writing to `useThemeStore`.
- [ ] 4.5 Move existing `/orgs/$slug/...` routes under `_app/orgs/$slug/...` (rename the files; TanStack route tree regenerates). Verify URLs are unchanged.
- [ ] 4.6 Strip the inline `<header>` + `<OrgSwitcher>` from `$slug.index.tsx` — the Topbar now hosts the switcher.

## 5. Settings layout + Branding panel

- [ ] 5.1 New pathless layout `_app/orgs/$slug/settings.tsx`:
  - Renders shadcn `<Tabs orientation="vertical">` with tabs for `Members`, `Branding`.
  - Active tab driven by URL.
- [ ] 5.2 Move `$slug.settings.members.tsx` to `$slug.settings.members.tsx` under the new layout (rename only — the layout wraps it).
- [ ] 5.3 New route `$slug.settings.branding.tsx` hosting `<ThemePicker>`.
- [ ] 5.4 `<ThemePicker>` component:
  - Radio cards for each of 5 presets (visual swatch + name).
  - Hover/focus calls `setPreviewPreset(preset)` on `<ThemeProvider>` context.
  - Mode-default selector (light/dark/system) below.
  - Save button → `PATCH /orgs/{slug}/theme` via the codegen client; on success, invalidates `useGetOrg` and clears preview.
  - Cancel button or Escape key reverts preview.
  - Disabled state for non-admins (capability check via `can()` exposed through a hook — see §5.5).
- [ ] 5.5 New hook `frontend/src/features/authz/useCan.ts`:
  - Wraps `GET /authz/check?op=&resource=&id=` (if exists; otherwise infer client-side via `useOrgStore` + `currentRole`). Verify which path is canonical before implementing.

## 6. Tests

- [ ] 6.1 Unit (frontend, vitest) — `lib/theme.ts` Zod schema accepts the 5 preset names + rejects `"neon"`.
- [ ] 6.2 Unit (frontend) — `useThemeStore` reads + writes localStorage; first-load defaults to `system` if no entry.
- [ ] 6.3 Unit (frontend) — `<ThemeProvider>` applies CSS vars on mount + on `setPreviewPreset` call (jsdom test asserting `document.documentElement.style` properties).
- [ ] 6.4 Backend integration — `PATCH /orgs/{slug}/theme` happy path: owner saves `corporate`, response 200, DB row updated, audit row appears with the right diff.
- [ ] 6.5 Backend integration — compliance officer hits the endpoint → 403; org theme unchanged.
- [ ] 6.6 Backend integration — invalid preset (`"neon"`) → 422; org theme unchanged.
- [ ] 6.7 E2E (Playwright) — owner navigates to Settings → Branding → picks `corporate` → reload → still corporate. Smoke only; visual regression is out of scope.

## 7. Documentation

- [ ] 7.1 Update root `CLAUDE.md` "Recipes" — add a snippet for "Add a Settings tab" pointing at `_app/orgs/$slug/settings.tsx`.
- [ ] 7.2 Add `frontend/src/features/theme/CLAUDE.md` (module guide) — preset map location, how to add a sixth preset (for the Phase 2 epic that ships next), provider mount point, hover-preview contract.
- [ ] 7.3 Update ADR-012 §"Phase 1" with `traces_to: openspec/changes/theme-tokens-and-app-shell` once this lands.

## 8. Validation + close-out

- [ ] 8.1 `openspec validate theme-tokens-and-app-shell --strict` passes.
- [ ] 8.2 `cd backend && uv run ruff check .` clean.
- [ ] 8.3 `./run_test.sh -q` green.
- [ ] 8.4 `cd frontend && npm run build` clean (tsc + vite).
- [ ] 8.5 `cd frontend && npm run lint` clean.
- [ ] 8.6 PR opened, linked to issue #5 (mention it's the first of two).
- [ ] 8.7 Archive change after merge; sync delta specs to `openspec/specs/design-system/spec.md` (new) + `openspec/specs/multi-tenancy/spec.md`.
