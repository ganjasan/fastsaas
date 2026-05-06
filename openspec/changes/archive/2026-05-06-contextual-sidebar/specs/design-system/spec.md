## ADDED Requirements

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
