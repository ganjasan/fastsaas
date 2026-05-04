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

