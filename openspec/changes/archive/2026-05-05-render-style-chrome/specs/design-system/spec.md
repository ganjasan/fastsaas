## ADDED Requirements

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
