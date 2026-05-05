## ADDED Requirements

### Requirement: Org admins can persist a theme choice via PATCH /orgs/{slug}/theme

The system SHALL expose `PATCH /orgs/{slug}/theme` accepting a body `{preset: string, mode_default?: "light" | "dark" | "system"}` where `preset` is one of `default`, `modern`, `corporate`, `dark`, `high-contrast`. The endpoint SHALL be gated on `Operation.ADMIN` over `ResourceType.ORGANISATION` for the slug-resolved org. On success the merged JSON SHALL be persisted into `organisations.theme` (replacing prior contents) and the response SHALL be HTTP 200 with the updated org payload.

#### Scenario: Owner saves a preset choice

- **GIVEN** an owner of `acme` (holds `admin:organisation`)
- **WHEN** they `PATCH /orgs/acme/theme` with body `{"preset": "corporate"}`
- **THEN** the response is HTTP 200 with the org payload reflecting `theme = {"preset": "corporate"}`
- **AND** `organisations.theme` for acme is now `{"preset": "corporate"}`

#### Scenario: Compliance officer cannot rebrand

- **GIVEN** a `role:compliance_officer` of `acme` (no `admin:organisation`)
- **WHEN** they call `PATCH /orgs/acme/theme` with a valid body
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`
- **AND** `organisations.theme` is unchanged

#### Scenario: Unknown preset is rejected

- **WHEN** an owner sends `{"preset": "neon-pink"}`
- **THEN** the response is HTTP 422 (Pydantic validation error on the enum)
- **AND** `organisations.theme` is unchanged

#### Scenario: Mode default persisted alongside preset

- **WHEN** an owner sends `{"preset": "modern", "mode_default": "dark"}`
- **THEN** the persisted `organisations.theme` equals `{"preset": "modern", "mode_default": "dark"}` (the request replaces, not merges)

### Requirement: Theme writes produce an audit row

The system SHALL emit one `audit_log` row with `entity_type = "organisation"` and `action = "update"` for every successful `PATCH /orgs/{slug}/theme` call. The `diff` SHALL show the before/after of the `theme` JSONB column.

#### Scenario: Theme update appears in compliance reads

- **WHEN** an owner sets `acme.theme = {"preset": "corporate"}` from a previous `{"preset": "default"}`
- **THEN** an `audit_log` row exists with `entity_type = "organisation"`, `entity_id = acme.id`, `action = "update"`, and `diff.before.theme = {"preset": "default"}` / `diff.after.theme = {"preset": "corporate"}`
