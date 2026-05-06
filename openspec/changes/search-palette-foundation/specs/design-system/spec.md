## ADDED Requirements

### Requirement: Command palette mounts inside `<Shell>` and consumes the registry

The system SHALL render a `<CommandPalette>` modal inside every `<Shell>` instance (AppShell, AdminShell, future flavours). Each Shell SHALL:

- Mount its own `<CommandPaletteHotkey>` global keydown listener that opens the palette on `Cmd+K` (Mac) / `Ctrl+K` (Win/Linux). The listener SHALL ignore the keypress when the focused element is an `<input>`, `<textarea>`, or `[contenteditable=true]` other than the palette's own input.
- Compose its own registry: `pagesRegistry` (static workspace nav like Overview / Projects / Settings), `actionsRegistry` (Create project / Create org / Switch workspace), and a `rendererRegistry: Map<entity_type, SearchResultRenderer>` for backend-returned hits.

Clicking `<SearchTrigger>` in the topbar SHALL open the same palette. The placeholder `⌘K` kbd hint becomes a real shortcut.

#### Scenario: ⌘K opens the palette anywhere in the dashboard

- **GIVEN** a user is on `/orgs/acme` (workspace context, AppShell)
- **WHEN** they press `Cmd+K`
- **THEN** the palette modal opens with a focused search input and Pages + Actions sections rendered

#### Scenario: ⌘K is suppressed inside text inputs

- **GIVEN** the user is typing into a project-name input
- **WHEN** they press `Cmd+K` while focused inside that input
- **THEN** the palette does NOT open (the keypress falls through to the input's normal behaviour; the user can still open the palette by clicking `<SearchTrigger>`)

#### Scenario: Esc closes the palette

- **GIVEN** the palette is open
- **WHEN** the user presses Escape
- **THEN** the palette closes and focus returns to the previously-focused element

### Requirement: Palette renders Pages + Actions sections without backend calls

The system SHALL render two static sections in the palette before any backend response:

- **Pages**: navigation entries declared in the active Shell's `pagesRegistry` (e.g. AppShell registers Overview / Projects / Settings → Members / Settings → Branding).
- **Actions**: command entries declared in the active Shell's `actionsRegistry` (e.g. AppShell registers Create project / Create organisation / Switch workspace → Acme / Switch workspace → Globex).

These render without firing a network request. They SHALL filter as the user types using a substring match on the entry's label.

#### Scenario: Empty query renders Pages + Actions

- **WHEN** the palette opens with an empty input
- **THEN** the rendered sections are Pages + Actions only — no backend hits, no spinner, no empty-state message
- **AND** typing one character continues to filter Pages + Actions client-side without firing a backend request

### Requirement: Palette fires backend search when query is at least 2 characters

The system SHALL fire `GET /search?q=` when the user's input length is `>= 2`. Below 2 chars no request is fired. Each backend group renders inline in the palette under its `label`, with rows produced by the active Shell's `rendererRegistry`.

#### Scenario: Two characters trigger a backend search

- **WHEN** the user types `q4` into the palette input
- **THEN** a request to `GET /search?q=q4` fires
- **AND** when the response arrives, sections for each non-empty group render below the static Pages + Actions sections

#### Scenario: Renderer registry maps entity_type to a row component

- **GIVEN** the active AppShell registry has a project renderer
- **WHEN** the response includes a `project` group
- **THEN** each project hit renders via the registry's project renderer (icon + title + subtitle); selecting it navigates to the hit's `href`

#### Scenario: Unknown entity_type falls back to a default renderer

- **GIVEN** the response includes a group with `entity_type = "scenario"` but the active registry has no renderer for it
- **WHEN** the palette renders the group
- **THEN** the default renderer is used (generic icon + title + subtitle); selecting still navigates to `href`
- **AND** a console warning is emitted noting the missing renderer registration

### Requirement: Recent searches persist per workspace

The system SHALL persist the user's last 10 distinct search queries per workspace slug in localStorage under key `fastsaas.searches`. The palette SHALL render these as a "Recent" section above Pages when the input is empty AND there are persisted queries for the active slug. Selecting a recent query refills the input and runs the search.

#### Scenario: Recent searches show only for the active workspace

- **GIVEN** the user previously searched `q4` in `acme` and `revenue` in `globex`
- **WHEN** they open the palette while in `acme`
- **THEN** the Recent section shows `q4` only (`globex`'s history is hidden until they switch back)
