## ADDED Requirements

### Requirement: Every domain mutation produces an audit row in the same transaction

The system SHALL append exactly one row to `audit_log` for every domain mutation initiated through the service layer, in the same database transaction as the mutation itself, so that the side effect and its audit trail commit or roll back together.

#### Scenario: Org create writes one create-organisation audit row

- **WHEN** `OrganisationService.create` succeeds for `slug = "acme"` initiated by HUMAN actor `A`
- **THEN** exactly one row exists in `audit_log` with `entity_type = "organisation"`, `entity_id = acme.id`, `action = "create"`, `actor_id = A`, `organisation_id = acme.id`
- **AND** the row's `timestamp` falls inside the same transaction as the `organisations` insert (asserted by the `id` ordering on `gen_random_uuid()` v7-style if v7 is enabled, or by `now() = audit.timestamp = org.created_at` rounded to the millisecond)

#### Scenario: Failed mutation produces no audit row

- **GIVEN** a slug-collision condition for `OrganisationService.create("dup")`
- **WHEN** the call raises `OrgSlugTakenError`
- **THEN** zero new rows exist in either `organisations` (excluding pre-existing) or `audit_log` (asserted by row-count diff before / after the call)

### Requirement: Sensitive fields never appear in audit diffs

The system SHALL apply a redaction step before writing `audit_log.diff`. The global denylist SHALL include at minimum `password_hash`, `token_hash`, `api_key_hash`, `key_hash`, `client_secret`, `raw_token`. Subclasses of `AuditedModel` MAY extend the denylist via `__audit_redact__`. Redacted fields SHALL appear in the stored `diff` with the literal value `"<redacted>"` so presence-of-key remains observable.

#### Scenario: User registration audit hides password_hash

- **WHEN** a new HUMAN actor registers (via the future audited registration flow, or via test setup that triggers `record(..., entity_type="user", action="create", diff=...)` with `password_hash` in `after`)
- **THEN** the resulting `audit_log.diff.after.password_hash` equals the literal string `"<redacted>"`, NEVER the Argon2 hash

#### Scenario: API key creation audit hides key_hash

- **WHEN** an `api_keys` row is created and an audit row is emitted (covered by the future API-keys epic; this scenario pins the redaction contract today)
- **THEN** `audit_log.diff.after.key_hash` equals `"<redacted>"`

### Requirement: `entity_type` is an open string vocabulary

The system SHALL accept any string for `audit_log.entity_type`. There SHALL be no DB-level CHECK constraint on the column. Convention enforced via review and the CLAUDE.md module guide: lowercase, singular, noun.

#### Scenario: Downstream entity type writes uneventfully

- **GIVEN** a downstream product defines `entity_type = "scenario"` for its domain
- **WHEN** the audit row is written via either `record(...)` or `AuditedModel`
- **THEN** the INSERT succeeds; the row is visible to org-scoped reads under the existing RLS policy

#### Scenario: Filter by entity_type works uniformly across core and downstream

- **GIVEN** an org has audit rows for both `entity_type = "project"` (core) and `entity_type = "scenario"` (downstream)
- **WHEN** a compliance-officer query selects `WHERE entity_type IN ('project', 'scenario')`
- **THEN** rows from both domains are returned without joins to per-domain tables

### Requirement: `actor` and `intent` flow through contextvars set by middleware

The system SHALL provide a FastAPI middleware (`AuditContextMiddleware`) that sets `actor_var` (current `CurrentActor` or `None`) and `intent_var` (`IntentContext` carrying `intent_hash` and `intent_metadata`) at the top of every request. Service-layer `record(...)` calls SHALL read these contextvars for default `actor` / `intent_hash` / `intent_metadata` when the caller does not pass explicit values.

#### Scenario: Middleware-set actor reaches the audit row

- **GIVEN** a request authenticated as actor `A` and routed through `AuditContextMiddleware`
- **WHEN** the route handler calls a service that invokes `record(..., entity_type="project", action="create", diff=...)` without passing `actor=`
- **THEN** the resulting audit row carries `actor_id = A` (read from `actor_var` inside `record`)

#### Scenario: `intent_hash` carries the right prefix per source

- **WHEN** the request includes `Idempotency-Key: ABC123`
- **THEN** every audit row written within the request has `intent_hash` starting with `idem:`
- **AND** when the request instead includes `X-Agent-Intent: <prompt>` the prefix is `agent:`
- **AND** when neither header nor session-intent is set the prefix is `req:`

### Requirement: Two write styles — explicit `record(...)` and `AuditedModel` mixin

The system SHALL provide two equivalent write APIs sharing the same redaction, contextvar, and transaction semantics:

- **Explicit**: `await audit.record(db, action, entity_type, entity_id, diff, ...)`. Used for non-CRUD operations and operations that span multiple ORM rows.
- **Mixin**: `class Foo(AuditedModel, table=True): __audit_entity_type__ = "foo"`. SQLAlchemy mapper-event listeners on `after_insert / after_update / after_delete` compute the diff from `inspect(target).attrs.<col>.history`, apply redaction, and write the audit row in the caller's transaction.

#### Scenario: Mixin emits a create row on a new ORM insert

- **GIVEN** a downstream `class Scenario(AuditedModel, table=True)` with `__audit_entity_type__ = "scenario"`
- **WHEN** a route handler creates a new `Scenario` instance and the session commits
- **THEN** an `audit_log` row with `entity_type = "scenario"`, `action = "create"`, full `diff.after` (less redacted fields), and the active actor exists in the same transaction

#### Scenario: Mixin distinguishes soft-delete from update

- **GIVEN** an `AuditedModel` subclass with a `deleted_at` column and a row whose `deleted_at` is currently NULL
- **WHEN** an UPDATE flips `deleted_at` from NULL to NOW
- **THEN** the emitted audit row has `action = "delete"`, NOT `action = "update"`

#### Scenario: `__audit_skip__` opts out cleanly

- **GIVEN** `class Cache(AuditedModel, table=True): __audit_skip__ = True`
- **WHEN** a `Cache` row is inserted, updated, or deleted
- **THEN** no audit row is written for any of those events

### Requirement: Audit log reads are tenant-scoped except for compliance-officer

The system SHALL preserve the existing RLS semantics on `audit_log`:
- Default policy: `organisation_id = current_setting('app.current_org', true)::uuid`.
- Compliance-officer escape hatch: `current_setting('app.role', true) = 'compliance_officer'` opens cross-org reads.

This change does not modify the migration; it pins the requirement so service-layer reads in this and future changes preserve it.

#### Scenario: Member sees only their org's audit rows

- **GIVEN** orgs `acme` and `globex` each have audit rows
- **WHEN** a member of `acme` (with `app.current_org = acme.id` pinned) selects from `audit_log`
- **THEN** only rows with `organisation_id = acme.id` are returned

#### Scenario: Compliance officer reads cross-org

- **GIVEN** an actor with `role:compliance_officer` capability
- **WHEN** the route sets `app.role = 'compliance_officer'` and selects from `audit_log` without a tenant filter
- **THEN** rows from every org the actor is a compliance officer for are returned (`organisation_id` not filtered by RLS)
