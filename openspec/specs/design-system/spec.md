# design-system Specification

## Purpose
TBD - created by archiving change theme-tokens-and-app-shell. Update Purpose after archive.
## Requirements
### Requirement: The application supports five pre-defined theme presets

The system SHALL ship exactly five theme presets — `default`, `modern`, `corporate`, `dark`, `high-contrast` — each declaring a complete CSS-variable set covering `--background`, `--foreground`, `--card`, `--card-foreground`, `--popover`, `--popover-foreground`, `--primary`, `--primary-foreground`, `--secondary`, `--secondary-foreground`, `--muted`, `--muted-foreground`, `--accent`, `--accent-foreground`, `--destructive`, `--destructive-foreground`, `--border`, `--input`, `--ring`, and `--radius`.

#### Scenario: Each preset is a fully populated token set

- **GIVEN** the preset enum
- **WHEN** the frontend imports the preset map
- **THEN** every preset name maps to an object whose keys cover every CSS variable in the token contract above (no preset is partial)

#### Scenario: An unknown preset name fails Zod validation

- **WHEN** server-side or client-side code parses `theme.preset = "neon"`
- **THEN** Zod validation rejects with a `presetUnknown` error
- **AND** the application falls back to `default` for rendering

### Requirement: Active preset and mode are applied via the document root

The system SHALL render every component under the AppShell using the active preset's CSS variables, applied via `document.documentElement.style.setProperty(...)`. The active mode (`light` | `dark`) SHALL toggle the `.dark` class on `<html>`.

#### Scenario: Switching preset changes brand colour live

- **GIVEN** the active preset is `default`
- **WHEN** a `<ThemeProvider>` consumer calls `setPreset("corporate")`
- **THEN** every CSS variable on `<html>` is replaced with the `corporate` preset's value within the same render frame (no reload)
- **AND** Tailwind utility classes like `bg-primary` resolve to the new value

#### Scenario: User mode toggle flips dark class

- **WHEN** the user toggles mode from `light` to `dark` via the Topbar control
- **THEN** the `dark` class is added to `<html>`
- **AND** components that use `dark:` Tailwind variants render their dark counterpart

#### Scenario: System mode follows prefers-color-scheme live

- **GIVEN** the user mode is `system`
- **WHEN** the OS-level dark-mode preference flips while the dashboard is mounted
- **THEN** the `.dark` class on `<html>` follows the new preference within one media-query callback (no reload)

### Requirement: Per-org preset choice persists across reloads

The system SHALL store the org's theme choice in `organisations.theme` JSONB as `{preset: string, mode_default?: "light" | "dark" | "system"}`. The frontend SHALL fetch this from `GET /orgs/{slug}` and apply it on every navigation into a route under `/_app/orgs/{slug}`.

#### Scenario: Reload preserves preset

- **GIVEN** an admin sets the org preset to `corporate` and clicks Save
- **WHEN** any user of the org reloads any `/orgs/{slug}/...` route
- **THEN** the rendered dashboard uses the `corporate` preset's CSS variables on first paint (server-pushed `theme.preset` is read from `GET /orgs/{slug}` and applied before component mount)

#### Scenario: Empty `theme` resolves to `default` preset

- **GIVEN** an org created before this change with `organisations.theme = '{}'::jsonb`
- **WHEN** a member loads the dashboard
- **THEN** `default` preset is applied; no error is thrown

### Requirement: Per-user mode choice persists in localStorage

The system SHALL store the user's mode choice (`light` | `dark` | `system`) in `localStorage` under key `theme.mode`. On first load with no entry, the user inherits `mode_default` from the active org's theme (defaulting to `system` if unset).

#### Scenario: First-load user inherits org default

- **GIVEN** an org with `theme.mode_default = "dark"` and a user with no `theme.mode` localStorage entry
- **WHEN** the user logs in and navigates to `/orgs/{slug}`
- **THEN** the dashboard renders in dark mode (the `.dark` class is on `<html>`)
- **AND** localStorage still has no `theme.mode` (org default did not write a per-user override)

#### Scenario: Per-user toggle wins over org default

- **GIVEN** the same org default `dark` and a user who toggled to `light` previously
- **WHEN** the user reloads
- **THEN** localStorage `theme.mode = "light"` wins; the dashboard renders in light mode

### Requirement: AppShell hosts every `/orgs/{slug}/*` route

The system SHALL provide a TanStack pathless layout `_app` that wraps every nested `/orgs/{slug}/*` route with a Sidebar (left, collapsible) and a Topbar (org switcher, user menu, theme-mode toggle). Routes outside the dashboard surface (`/login`, `/orgs` list, `/orgs/new`, `/accept-invite/{token}`, `/accept-share/{token}`) SHALL NOT render the AppShell.

#### Scenario: Dashboard route shows the shell

- **WHEN** the user navigates to `/orgs/acme/projects`
- **THEN** the page renders inside the AppShell (Sidebar + Topbar visible)

#### Scenario: Login route bypasses the shell

- **WHEN** an unauthenticated user navigates to `/login`
- **THEN** the page renders without the AppShell — no Sidebar, no Topbar

### Requirement: Sidebar collapse persists per-user above `lg:` breakpoint

The system SHALL persist the Sidebar collapsed/expanded state in `localStorage` under `appShell.sidebarCollapsed` (boolean). At viewport widths below `lg` (1024px), the Sidebar SHALL render as a Sheet (slide-in drawer) instead of a collapsed rail.

#### Scenario: Collapse persists across reloads

- **GIVEN** the user clicks the collapse toggle at `lg+` viewport
- **WHEN** they reload the page
- **THEN** the Sidebar starts collapsed

#### Scenario: Below `lg`, Sidebar is a Sheet

- **GIVEN** the viewport width is 800px
- **WHEN** the page mounts
- **THEN** the Sidebar trigger opens a `sheet` (slide-in drawer), not a collapsed rail

### Requirement: Settings layout uses vertical tabs

The system SHALL provide a Settings layout at `/orgs/{slug}/settings` rendering vertical tabs (`Members`, `Branding`) on the left and the active panel on the right. Members SHALL host the existing membership-management UI; Branding SHALL host the `<ThemePicker>`.

#### Scenario: Active tab matches the URL

- **WHEN** the user navigates to `/orgs/acme/settings/branding`
- **THEN** the `Branding` tab is highlighted as active and the panel renders the `<ThemePicker>`

#### Scenario: Switching tabs changes URL

- **WHEN** the user clicks the `Members` tab from the Branding panel
- **THEN** the URL becomes `/orgs/acme/settings/members` (TanStack Link, not a hash)

### Requirement: ThemePicker live-previews on hover and persists on confirm

The system SHALL render a `<ThemePicker>` in the Branding panel showing radio cards for each preset and a separate selector for `mode_default`. Hover/focus on a preset card SHALL provisionally apply that preset's CSS variables to the document root; clicking outside or pressing Escape SHALL revert to the last persisted preset; clicking Save SHALL `PATCH /orgs/{slug}/theme` with the chosen preset and `mode_default`.

#### Scenario: Hover previews preset

- **GIVEN** the active org preset is `default`
- **WHEN** the admin hovers over the `corporate` card
- **THEN** the dashboard chrome behind the picker re-themes to corporate live (no save yet)

#### Scenario: Cancel reverts the preview

- **GIVEN** the admin previewed `corporate` but did NOT click Save
- **WHEN** they click Cancel or press Escape
- **THEN** the dashboard reverts to `default` (the last persisted preset)

#### Scenario: Save persists and propagates

- **GIVEN** the admin previewed `corporate` and clicks Save
- **WHEN** the request `PATCH /orgs/acme/theme` returns 200
- **THEN** the org store updates with the new `theme.preset = "corporate"` and the change is immediately visible to other tabs/users on next reload

