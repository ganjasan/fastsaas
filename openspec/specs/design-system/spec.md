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

### Requirement: A reusable `<Shell>` primitive hosts every dashboard surface

The system SHALL provide a single layout primitive `<Shell>` (`frontend/src/components/layout/Shell.tsx`) parameterised by named slot props: `sidebarHeader`, `sidebarSections` (array of `{label?, items}`), `sidebarBottom`, `topbarLeft`, `topbarRight`, and `children`. `<AppShell>` (org dashboard) and any future shell flavour SHALL be thin wrappers around `<Shell>` that supply the slot content; the layout itself SHALL NOT diverge between consumers.

#### Scenario: Two consumers share the same primitive

- **GIVEN** the codebase contains `<AppShell>` and (in a future change) `<AdminShell>`
- **WHEN** the layout DOM is inspected
- **THEN** both render through `<Shell>` with the same outer structure (sidebar grid + topbar + main outlet)
- **AND** their differences appear only in the slot content (workspace header, nav sections, topbar controls)

#### Scenario: A nav section without a label renders as a flat list

- **GIVEN** an `<AppShell>` consumer passes `sidebarSections = [{ items: [Projects, Settings] }]` (no label)
- **WHEN** the sidebar renders
- **THEN** the two items render directly under the workspace header with no UPPERCASE label above them

#### Scenario: A nav section with a label renders an UPPERCASE caption

- **GIVEN** a consumer passes `sidebarSections = [{ label: "OPERATIONS", items: [...] }, { label: "CONFIGURATION", items: [...] }]`
- **WHEN** the sidebar renders
- **THEN** each section renders an UPPERCASE muted label above its items

### Requirement: Workspace switcher lives in the sidebar header

The system SHALL render a `<WorkspaceSwitcher>` component in the AppShell's sidebar header slot, displaying an avatar tile (workspace initial), the workspace name, and a chevron. Clicking SHALL open a dropdown listing the user's organisations + a "Create new organisation" action. The Topbar SHALL NOT render the workspace switcher.

#### Scenario: Workspace switcher renders in the sidebar

- **GIVEN** a logged-in user with one or more organisations and an active org slug
- **WHEN** they navigate into `/orgs/{slug}/...`
- **THEN** the sidebar header shows `[avatar] <workspace name> ⌄`
- **AND** the topbar does not contain an org switcher

#### Scenario: Switcher dropdown lists orgs and a create action

- **WHEN** the user clicks the workspace switcher
- **THEN** the dropdown shows every org they belong to (with the active one highlighted) and a "Create new organisation" entry pointing to `/orgs/new`

### Requirement: Topbar carries breadcrumb (left) + global controls (right)

The system SHALL render the topbar with two slots: left (breadcrumb / current section name derived from the URL) and right (Search trigger + `+ New ⌄` dropdown + ThemeModeToggle + user menu). The topbar SHALL NOT host the workspace switcher.

#### Scenario: Breadcrumb reflects the current section

- **GIVEN** the user is on `/orgs/acme/projects`
- **WHEN** the topbar renders
- **THEN** the left slot shows `Projects`

#### Scenario: Topbar right slot exposes Search, +New, theme toggle, user menu

- **WHEN** the topbar renders
- **THEN** the right slot contains, in order: a Search button (with `⌘K` shortcut hint), a `+ New ⌄` dropdown, a theme-mode toggle, and a user-menu trigger

#### Scenario: Search trigger is a placeholder no-op in v1

- **GIVEN** the user clicks the Search button (or presses `⌘K`)
- **WHEN** the handler runs
- **THEN** no command palette opens (placeholder); the contract pins this so a future epic ships the real palette without breaking the trigger surface

### Requirement: Sidebar bottom-chrome surfaces operator controls

The system SHALL render below the nav sections a bottom-chrome group containing a Status pill (static "All systems operational" with a green dot in v1; wired to `/api/admin/health` in #20), a Changelog link, a Help / Contact support link, and a Collapse toggle.

#### Scenario: Status pill is visible and static in v1

- **WHEN** the sidebar renders
- **THEN** the bottom chrome contains a green-dot pill labelled "All systems operational"

#### Scenario: Collapse toggle moves between collapsed-rail and expanded states

- **WHEN** the user clicks the Collapse toggle at `lg+` viewport
- **THEN** the sidebar transitions to a 16-rem icon-only rail (`lg:w-16`) and the workspace switcher in the header collapses to its avatar-only form
- **AND** the toggle's icon flips direction so a second click expands it again

### Requirement: Active nav item uses brand colour, not neutral accent

The system SHALL render the active nav item with `bg-primary/10` background and `text-primary` foreground (matching the active preset's brand colour). Hover-only state SHALL continue to use `bg-accent`. The active state and the hover state MUST be visually distinct.

#### Scenario: Active route is brand-coloured

- **GIVEN** the active route is `/orgs/acme/projects`
- **WHEN** the Projects nav item renders
- **THEN** its background is `bg-primary/10` and its text is `text-primary` (resolves through `<ThemeProvider>` to the active org's preset)

#### Scenario: Hover on a non-active item is accent-coloured

- **WHEN** the user hovers a non-active nav item
- **THEN** its background is `bg-accent` (clearly distinct from the active state)

### Requirement: Org overview shows projects with a "Create new" tile

The system SHALL render `/orgs/{slug}` as an Overview page with H1 "Overview", a right-aligned `+ New ⌄` dropdown, and a "Projects" subsection containing one card per existing project plus a final dashed-bordered tile labelled `+ Create new project`. Clicking a project card SHALL navigate to its detail route. Clicking the dashed tile SHALL open the same create-project dialog as the Projects page.

#### Scenario: Overview lists existing projects

- **GIVEN** an org has three projects
- **WHEN** the user opens `/orgs/{slug}`
- **THEN** the Projects subsection renders three cards (name + slug + description) followed by the dashed `+ Create new project` tile

#### Scenario: Overview empty state shows just the create tile

- **GIVEN** an org with zero projects
- **WHEN** the user opens `/orgs/{slug}`
- **THEN** the Projects subsection renders only the dashed `+ Create new project` tile

#### Scenario: Dashed tile opens the create dialog

- **WHEN** the user clicks the dashed tile
- **THEN** the same create-project dialog used elsewhere opens, prefilled with the active org slug

### Requirement: Sidebar nav swaps to project-scoped items inside a project

The system SHALL render two distinct nav-section sets in the workspace AppShell sidebar based on the active URL:

- **Workspace context** — when the URL is NOT under `/orgs/{slug}/projects/{projectSlug}/...`. Renders the workspace nav (Overview / Projects / Settings).
- **Project context** — when the URL is under `/orgs/{slug}/projects/{projectSlug}/...`. Renders a "← Back to projects" anchor + an UPPERCASE-labelled section bearing the project's slug + project-scoped items (Overview, Sharing). The workspace nav SHALL NOT be visible.

#### Scenario: Workspace nav on the workspace overview

- **GIVEN** a logged-in member is at `/orgs/acme`
- **WHEN** the AppShell renders
- **THEN** the sidebar shows three items: Overview, Projects, Settings

#### Scenario: Project nav on a project page

- **GIVEN** a logged-in member is at `/orgs/acme/projects/alpha`
- **WHEN** the AppShell renders
- **THEN** the sidebar's workspace nav is replaced with `← Back to projects` + an UPPERCASE label `ALPHA` + Overview + Sharing
- **AND** the workspace nav items (Overview / Projects / Settings of the org) are NOT in the sidebar

#### Scenario: Sharing tab is reachable via the sidebar

- **GIVEN** the user is at `/orgs/acme/projects/alpha`
- **WHEN** they click `Sharing` in the project sidebar
- **THEN** the URL becomes `/orgs/acme/projects/alpha/sharing`
- **AND** the `<ProjectSharing>` component renders in the page body
- **AND** the sidebar's `Sharing` item is in the active state

#### Scenario: Back-to-projects exits the project context

- **GIVEN** the user is at any URL under `/orgs/acme/projects/alpha`
- **WHEN** they click `Back to projects` in the project sidebar
- **THEN** the URL becomes `/orgs/acme/projects`
- **AND** the sidebar swaps back to the workspace nav

### Requirement: Project page exposes Overview + Sharing as discrete subroutes

The system SHALL render `/orgs/{slug}/projects/{projectSlug}/` as a project-detail layout that wraps two subroutes via Outlet:

- **Index** (`/orgs/{slug}/projects/{projectSlug}/`) — the Overview body (analyses / scenarios / runs placeholder until those land).
- **Sharing** (`/orgs/{slug}/projects/{projectSlug}/sharing`) — the `<ProjectSharing>` body (per #30).

The parent layout SHALL fetch the project once, expose it via `useProjectContext()`, and render the project header (name, slug, description) above the Outlet.

#### Scenario: Layout fetches once and exposes via context

- **GIVEN** the user navigates from Overview to Sharing under the same project
- **WHEN** TanStack Router matches the new subroute
- **THEN** the project query does NOT re-fire (the parent layout's query is cached)
- **AND** the project header (name, slug, description) remains rendered without a remount flicker

