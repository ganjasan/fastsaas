## ADDED Requirements

### Requirement: Actors carry a `is_platform_staff` boolean

The system SHALL store on each `actors` row a column `is_platform_staff: BOOLEAN NOT NULL DEFAULT FALSE`. The flag SHALL be toggled out-of-band (CLI seed in v1; in-UI promotion in a future epic). No existing row SHALL be promoted by the migration.

#### Scenario: Migration adds the column with FALSE default

- **GIVEN** a database upgraded from migration 0007 to 0008
- **WHEN** the migration runs
- **THEN** every existing actor row has `is_platform_staff = FALSE`
- **AND** new actors created without specifying the flag have `is_platform_staff = FALSE`

#### Scenario: CLI seed promotes a user to platform staff

- **GIVEN** an existing user `alice@example.com` with `is_platform_staff = FALSE`
- **WHEN** the operator runs `make seed-platform-staff USER_EMAIL=alice@example.com`
- **THEN** the actor row's `is_platform_staff` becomes TRUE
- **AND** one `audit_log` row is appended with `entity_type = "actor"`, `action = "update"`, `diff = {"before": {"is_platform_staff": false}, "after": {"is_platform_staff": true}}`

#### Scenario: CLI rejects an unknown email

- **WHEN** the operator runs `make seed-platform-staff USER_EMAIL=ghost@example.com` for an email that has no user
- **THEN** the script exits non-zero with a `user not found` error
- **AND** no actor row is modified

### Requirement: `/api/admin/me` gates the admin surface

The system SHALL expose `GET /api/admin/me` returning `{actor_id, email, display_name, is_platform_staff: true}` for platform-staff actors. For non-staff (or unauthenticated) callers it SHALL return HTTP 403 with `code = "authz.forbidden"` (or HTTP 401 if no token).

#### Scenario: Staff actor reads /api/admin/me

- **GIVEN** a verified user with `is_platform_staff = TRUE` and a valid access token
- **WHEN** they `GET /api/admin/me`
- **THEN** the response is HTTP 200 with `{actor_id, email, display_name, is_platform_staff: true}`

#### Scenario: Org owner who is not staff is rejected

- **GIVEN** an org owner (full org bundles) with `is_platform_staff = FALSE`
- **WHEN** they `GET /api/admin/me`
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`

#### Scenario: Unauthenticated request is rejected

- **WHEN** an unauthenticated caller `GET /api/admin/me`
- **THEN** the response is HTTP 401 with `code = "auth.token_missing"`

### Requirement: Admin shell renders for staff and 403/redirects others

The system SHALL provide a frontend route tree under `/admin/*` rendering an admin shell with sidebar items: `Orgs`, `Metrics`, `Health`, `Design system`, `Auth`, `OAuth providers`. Each sub-route SHALL render a placeholder card pointing at the issue that fills it. The shell SHALL be gated on the result of `GET /api/admin/me`: non-staff users SHALL be redirected to `/orgs` (their normal landing); unauthenticated users SHALL be redirected to `/auth/login`.

#### Scenario: Staff lands on /admin and sees the shell

- **GIVEN** a staff actor logged in
- **WHEN** they navigate to `/admin`
- **THEN** the AdminShell renders with the six sidebar items
- **AND** the default sub-route shows the `Orgs` placeholder card

#### Scenario: Non-staff is redirected away

- **GIVEN** an org member with `is_platform_staff = FALSE`
- **WHEN** they navigate to `/admin/orgs`
- **THEN** the frontend issues a navigation to `/orgs` (their normal dashboard)

#### Scenario: Unauthenticated user is sent to login

- **GIVEN** no access token
- **WHEN** the user navigates to `/admin`
- **THEN** the frontend issues a navigation to `/auth/login`

### Requirement: Admin shell renders with a fixed neutral theme, not org branding

The system SHALL render the AdminShell with the `default` preset inline (not via the per-org `<ThemeProvider>`). The light/dark mode toggle SHALL still work (it is per-user, not per-org). This ensures platform staff visually distinguish admin work from org-scoped work.

#### Scenario: Admin shell ignores org theme

- **GIVEN** an org with `theme.preset = "corporate"` and a staff member who is also a member of that org
- **WHEN** the staff navigates to `/admin/orgs`
- **THEN** the rendered chrome uses the `default` preset's CSS variables, NOT `corporate`'s
