# multi-tenancy Specification

## Purpose
TBD - created by archiving change multi-tenant-orgs-and-capabilities. Update Purpose after archive.
## Requirements
### Requirement: Organisation as the top-level tenant

The system SHALL persist every tenant as a row in `organisations` with a globally-unique URL-safe `slug`. All tenant-scoped data SHALL transitively reference an organisation via `organisation_id` foreign keys.

#### Scenario: Org slug is unique and URL-safe

- **WHEN** a HUMAN actor creates an org with `slug = "acme-co"`
- **THEN** a row is inserted into `organisations` with that slug, the actor is added to `organisation_members`, and `role:owner` capabilities are minted to the actor
- **AND** a second create attempt with the same slug fails with HTTP 409 `code = "org.slug_taken"`

#### Scenario: Reserved slugs are rejected

- **WHEN** a create-org request uses `slug = "admin"` (in the reserved list)
- **THEN** the response is HTTP 400 with `code = "org.slug_reserved"`
- **AND** no row is inserted

#### Scenario: Malformed slug is rejected

- **WHEN** a create-org request uses `slug = "Bad Slug!"`
- **THEN** the response is HTTP 400 with `code = "org.slug_invalid"` (regex `^[a-z0-9-]{3,63}$` enforced)

### Requirement: Project belongs to exactly one organisation

The system SHALL persist projects in a `projects` table with `organisation_id NOT NULL` and `(organisation_id, slug)` unique. A project SHALL NOT exist outside an organisation.

#### Scenario: Project slug unique within org but not globally

- **WHEN** organisations `acme` and `globex` both create a project with `slug = "platform"`
- **THEN** both inserts succeed, each scoped to its own org
- **AND** a second `platform` project under `acme` fails with HTTP 409 `code = "project.slug_taken"`

#### Scenario: Project create requires write capability

- **WHEN** a `role:viewer` member calls `POST /orgs/{slug}/projects`
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`
- **AND** no row is inserted

### Requirement: Organisation membership is explicit and revocable

The system SHALL track org membership via `organisation_members` rows. Adding a member SHALL be a deliberate action (create, accept invite, accept guest share). Removing a member SHALL revoke all capabilities granted to them within that org.

#### Scenario: Inviter sends invitation; recipient accepts and gains role:member

- **WHEN** an `role:admin` member calls `POST /orgs/acme/members/invite { email: "x@example.com", role: "member" }`
- **THEN** an `org_invitation` magic-link is issued with 7-day TTL and emailed to that address
- **AND** when the recipient registers (or logs in) and submits the token to `/orgs/acme/members/accept`
- **THEN** an `organisation_members` row is inserted and `role:member` bundle capabilities are minted to the recipient

#### Scenario: Removing a member revokes bundles

- **WHEN** an admin calls `DELETE /orgs/acme/members/{actor_id}`
- **THEN** the `organisation_members` row is deleted
- **AND** every capability row for that actor with `metadata.org_id = acme.id` has `revoked_at` set
- **AND** the cached capability set in Redis is invalidated immediately

#### Scenario: Last owner cannot be removed

- **WHEN** an org has exactly one `role:owner` member and an attempt is made to remove them
- **THEN** the response is HTTP 409 with `code = "org.last_owner"`
- **AND** no rows are modified

### Requirement: RLS enforces tenant isolation at the database layer

The system SHALL enable Postgres RLS on `organisations`, `projects`, `organisation_members`, and `capabilities`. The `app_user` Postgres role SHALL NOT have `BYPASSRLS`; every request SHALL `SET LOCAL app.current_org` after verifying membership.

#### Scenario: Cross-tenant SELECT returns nothing under app_user

- **GIVEN** organisations `acme` and `globex` each with one project
- **WHEN** the request context is `app.current_org = acme.id` and the application executes `SELECT * FROM projects`
- **THEN** only `acme`'s projects are returned, regardless of any application WHERE clause

#### Scenario: Tenant-context middleware sets app.current_org per transaction

- **WHEN** an authenticated request to `GET /orgs/acme/projects` arrives with `X-Org: acme`
- **THEN** the tenant-context middleware verifies the actor's membership and runs `SET LOCAL app.current_org = '<uuid>'` before the route handler executes

#### Scenario: Non-member request to known org returns 404

- **WHEN** an actor not in `organisation_members` for `acme` calls `GET /orgs/acme/projects`
- **THEN** the response is HTTP 404 with `code = "org.not_found_or_forbidden"` (existence is not disclosed per ADR-007)

### Requirement: Org switcher pins org context per request

The frontend SHALL pin the current org slug in client state and SHALL inject `X-Org: <slug>` on every API call. The backend SHALL accept this header to set `app.current_org` for the request lifetime.

#### Scenario: First login with no orgs shows empty-state

- **WHEN** a freshly-registered HUMAN actor with no `organisation_members` rows lands on `/orgs`
- **THEN** the page shows an empty-state CTA "Create your first organisation"
- **AND** no `X-Org` header is sent until an org is created or selected

#### Scenario: Switching orgs swaps the request header

- **GIVEN** a HUMAN actor is a member of `acme` and `globex`
- **WHEN** the user selects `globex` in the org switcher
- **THEN** subsequent API calls carry `X-Org: globex`
- **AND** the persisted preference survives a tab reload (Zustand `persist` to localStorage)

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

### Requirement: Project share-create response carries a one-time raw token

The system SHALL extend `ProjectShareResponse` (returned by `POST /orgs/{slug}/projects/{slug}/shares`) with a `raw_token: str` field carrying the freshly minted invite token. This is a one-time disclosure: the backend stores `sha256(token)` and never re-discloses it. The list endpoint (`GET .../shares` returning `ProjectShareItem`) SHALL NOT carry the field.

#### Scenario: Create response includes the email-delivered token

- **GIVEN** an owner shares project `alpha` with `guest@example.com`
- **WHEN** `POST /orgs/acme/projects/alpha/shares` returns 201
- **THEN** the response body contains `raw_token` equal to the token in the email-delivered invite link

#### Scenario: List response omits the raw token

- **GIVEN** a previously created share
- **WHEN** `GET /orgs/acme/projects/alpha/shares` returns 200
- **THEN** each list item contains `id`, `email`, `shared_by`, `expires_at`, `created_at`
- **AND** no item carries a `raw_token` field

### Requirement: Project page surfaces a sharing section for capable actors

The system SHALL render a `<ProjectSharing>` section on `/orgs/{slug}/projects/{projectSlug}` containing an "Invite a guest" form (email + TTL selector + Share button) and a "Pending invites" list with revoke actions. The form submits to the existing share endpoint; the list reads from the existing list endpoint; revoke calls the existing delete endpoint.

#### Scenario: Owner sees the sharing section

- **GIVEN** an owner of org `acme` opens project `alpha`
- **WHEN** the page renders
- **THEN** the Sharing section is visible with the invite form and the empty-state pending-invites list

#### Scenario: Successful share reveals copyable link once

- **GIVEN** the owner submits the form for `guest@example.com` with TTL 14 days
- **WHEN** the request returns 201
- **THEN** a reveal panel renders with a `readOnly` input containing `${origin}/orgs/accept-share/${raw_token}`
- **AND** a Copy button writes the link to the clipboard
- **AND** a Dismiss button removes the reveal panel
- **AND** an entry for `guest@example.com` appears in the pending-invites list

#### Scenario: Revoke invalidates the pending share

- **GIVEN** the operator clicks Revoke on a pending share for `guest@example.com`
- **WHEN** they confirm in the browser dialog
- **THEN** `DELETE /orgs/{slug}/projects/{slug}/shares/{share_id}` is issued
- **AND** the row disappears from the pending list on success

#### Scenario: Non-capable actor hits 403 on submit

- **GIVEN** a `role:viewer` actor (no `share:project` capability) opens the project page
- **WHEN** they submit the invite form
- **THEN** the request returns 403 `authz.forbidden`
- **AND** an error message appears under the form (UI does not pre-hide the section in v1; backend enforces)

