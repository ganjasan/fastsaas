# actor-identity Specification

## Purpose
TBD - created by archiving change identity-and-auth. Update Purpose after archive.
## Requirements
### Requirement: Actor parent table with type discriminator

The system SHALL persist every authenticated principal as a row in `actors`, with `actor_type` discriminating between HUMAN, AGENT, and SERVICE subtypes per ADR-009 and its amendment. All foreign keys from audit, ownership, and membership tables SHALL reference `actors.id` regardless of subtype.

#### Scenario: HUMAN actor row exists for every registered user

- **WHEN** a new user successfully registers
- **THEN** exactly one row exists in `actors` with `actor_type = 'HUMAN'` and `parent_actor_id IS NULL`
- **AND** exactly one row exists in `users` with `actor_id` equal to the new actor's id

#### Scenario: AGENT and SERVICE creation is disabled in v1

- **WHEN** any v1 API endpoint attempts to insert an `actor_type = 'AGENT'` or `'SERVICE'` row
- **THEN** the operation is rejected at the application layer with HTTP 501 "AGENT/SERVICE actors are deferred to a later release"
- **AND** the database CHECK constraints permit the values, leaving the schema ready for the future epic

### Requirement: CTI invariants enforced at the database

The system SHALL enforce CTI invariants via database constraints so that application bugs cannot create inconsistent rows.

#### Scenario: HUMAN cannot have parent_actor_id

- **WHEN** an INSERT attempts `actor_type = 'HUMAN'` with non-null `parent_actor_id`
- **THEN** the database rejects the insert via `human_no_parent` CHECK constraint

#### Scenario: AGENT must have parent_actor_id

- **WHEN** an INSERT attempts `actor_type = 'AGENT'` with null `parent_actor_id`
- **THEN** the database rejects the insert via `agent_has_parent` CHECK constraint

#### Scenario: Deleting actor cascades to subtype row

- **WHEN** a row in `actors` is deleted
- **THEN** any matching row in `users`, `agents`, or `services` is removed by ON DELETE CASCADE

### Requirement: current_actor dependency

The backend SHALL expose a FastAPI dependency `current_actor` that resolves the calling actor from a request's bearer token and returns a typed `CurrentActor` view (id, type, parent_actor_id, email, email_verified). Routes MAY compose `require_human` and `require_verified_email` guards on top.

#### Scenario: Valid bearer token resolves to actor

- **WHEN** a request carries `Authorization: Bearer <valid access JWT>`
- **THEN** `current_actor` returns a `CurrentActor` view with fields populated from `actors` joined with `users`

#### Scenario: Missing token returns 401

- **WHEN** a request has no `Authorization` header on a route depending on `current_actor`
- **THEN** the response is HTTP 401 with code `auth.token_missing`

#### Scenario: Expired access token returns 401

- **WHEN** a request carries an access JWT whose `exp` is in the past
- **THEN** the response is HTTP 401 with code `auth.token_expired`
- **AND** the response does NOT auto-refresh server-side

#### Scenario: require_verified_email guard rejects unverified email

- **WHEN** a request reaches a route guarded by `require_verified_email`
- **AND** the resolved actor's `users.email_verified` is FALSE
- **THEN** the response is HTTP 403 with code `auth.email_unverified`

### Requirement: Soft-delete semantics

The system SHALL treat `actors.deleted_at IS NOT NULL` as soft-deleted. Soft-deleted actors SHALL NOT authenticate.

#### Scenario: Soft-deleted user cannot log in

- **WHEN** a login attempt resolves to an actor with `deleted_at IS NOT NULL`
- **THEN** login fails with HTTP 401 code `auth.account_disabled`
- **AND** no JWT is issued

#### Scenario: Soft-deleted actor's bearer token is rejected

- **WHEN** a previously valid access JWT belongs to an actor whose `deleted_at` was just set
- **THEN** subsequent requests using that token are rejected with HTTP 401 `auth.account_disabled` until the token expires

