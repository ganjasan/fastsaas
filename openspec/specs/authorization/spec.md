# authorization Specification

## Purpose
TBD - created by archiving change multi-tenant-orgs-and-capabilities. Update Purpose after archive.
## Requirements
### Requirement: Capability is the only authorization primitive

The system SHALL store every authorization grant as a row in `capabilities` per ADR-013. Application code SHALL call a single function `can(actor, operation, resource_type, resource_id?) -> bool` to gate access. Direct queries against the `capabilities` table from route handlers are forbidden by code review.

#### Scenario: can() returns true when matching capability exists

- **GIVEN** an actor holds a capability `(operation='read', resource_type='project', resource_id=NULL)` not revoked, not expired, not policy-blocked
- **WHEN** the application calls `can(actor, 'read', 'project', any_uuid)`
- **THEN** it returns `True`

#### Scenario: can() returns false when capability is revoked

- **GIVEN** the same capability with `revoked_at = NOW() - INTERVAL '1 minute'`
- **WHEN** the application calls `can(actor, 'read', 'project', any_uuid)`
- **THEN** it returns `False`

#### Scenario: can() returns false when capability is expired

- **GIVEN** the same capability with `expires_at = NOW() - INTERVAL '1 minute'`
- **WHEN** the application calls `can(...)`
- **THEN** it returns `False`

#### Scenario: can() returns false when capability is policy-blocked

- **GIVEN** the same capability with `policy_blocked = TRUE`
- **WHEN** the application calls `can(...)`
- **THEN** it returns `False`

#### Scenario: Resource-scoped capability rejects other resources

- **GIVEN** an actor holds `(read, project, resource_id=P1)` only
- **WHEN** the application calls `can(actor, 'read', 'project', P2)`
- **THEN** it returns `False`

### Requirement: Role bundles are the provisioning surface

The system SHALL define role bundles `role:owner`, `role:admin`, `role:member`, `role:viewer`, `role:guest_viewer`, `role:compliance_officer` in code. Assigning a role SHALL mint all capabilities in its bundle, each tagged with `bundle_name`. Changing a role SHALL revoke the prior bundle and mint the new one.

#### Scenario: Creating an org mints role:owner to the creator

- **WHEN** a HUMAN actor calls `POST /orgs { name: "Acme", slug: "acme" }`
- **THEN** an `organisations` row is inserted, an `organisation_members` row is inserted, and capability rows for every entry of the `role:owner` bundle are inserted with `bundle_name = 'role:owner'` and `metadata.org_id = acme.id`

#### Scenario: Changing a role revokes the old bundle

- **GIVEN** an actor with active `role:member` bundle in org `acme`
- **WHEN** an admin calls `PATCH /orgs/acme/members/{actor_id} { role: "viewer" }`
- **THEN** every capability with `bundle_name = 'role:member'` and `metadata.org_id = acme.id` for that actor has `revoked_at` set
- **AND** new capabilities for `role:viewer` are minted with `metadata.org_id = acme.id`

#### Scenario: Project create propagates all_in_org bundles

- **GIVEN** org `acme` has 5 active members holding `role:member` (which contains `(write, project, all_in_org)`)
- **WHEN** an admin creates a new project `platform`
- **THEN** for each of the 5 actors, a capability row is inserted with `(operation='write', resource_type='project', resource_id=platform.id, bundle_name='role:member')`

### Requirement: Per-project guest pattern

The system SHALL allow inviting a non-member to a single project (UC-001). The invitation SHALL mint exactly one `role:guest_viewer` capability scoped to that project, without inserting an `organisation_members` row. The guest SHALL be able to read the project and SHALL NOT be able to list or read the org or its other projects.

#### Scenario: Guest accepts share and gets read on one project

- **WHEN** a `role:admin` calls `POST /orgs/acme/projects/platform/share { email: "guest@example.com" }`
- **THEN** a magic-link with `purpose = 'project_share'` and `metadata.project_id = platform.id` is issued and emailed
- **AND** when the recipient (registered HUMAN actor) submits the token, exactly one capability is minted: `(read, project, resource_id=platform.id, bundle_name='role:guest_viewer')`
- **AND** no `organisation_members` row is created

#### Scenario: Guest cannot list other projects in the org

- **GIVEN** the guest from the previous scenario
- **WHEN** the guest calls `GET /orgs/acme/projects`
- **THEN** the response contains only `platform`, never the other projects in `acme`

#### Scenario: Guest revocation takes effect immediately

- **WHEN** an admin revokes the guest's capability via `DELETE /orgs/acme/projects/platform/shares/{capability_id}`
- **THEN** the capability row has `revoked_at` set, the cached capability set is invalidated, and the next request from the guest returns HTTP 404 (`org.not_found_or_forbidden`)

### Requirement: Capability cache is invalidated on every mutation

The system SHALL cache the materialised capability set per actor in Redis with 5-minute TTL. Every grant (`mint_bundle`, `mint_capability`) and every revocation (`revoke_bundle`, `revoke_capability`, member removal, project soft-delete) SHALL invalidate the cache key for the affected actor before the response is sent.

#### Scenario: Cache miss falls through to DB and populates

- **GIVEN** an actor with no cached entry in Redis
- **WHEN** `can()` is called the first time
- **THEN** the actor's capabilities are loaded from `capabilities` (filtered by `revoked_at IS NULL AND policy_blocked = FALSE`), serialised to Redis with TTL 300 s, and the answer returned

#### Scenario: Mutation invalidates cache before response

- **GIVEN** an actor with capabilities cached in Redis
- **WHEN** an admin calls `DELETE /orgs/acme/members/{actor_id}` for that actor
- **THEN** the cache key `caps:{actor_id}` is deleted before the HTTP response is returned
- **AND** the next `can()` call for that actor reloads from DB

#### Scenario: Concurrent cache misses do not stampede

- **GIVEN** the cache key for an actor is empty and 50 concurrent requests trigger `can()` for the same actor
- **THEN** at most one DB load executes (SETNX-guarded); the other 49 wait briefly and read the populated cache

### Requirement: FastAPI dependency enforces capability at the route boundary

The system SHALL expose `require_capability(operation, resource_type)` as a FastAPI dependency. Routes SHALL apply it to gate access. A failed check SHALL return HTTP 403 with `code = "authz.forbidden"`.

#### Scenario: Member without write gets 403 on project create

- **GIVEN** an actor holds `role:viewer` in org `acme`
- **WHEN** they call `POST /orgs/acme/projects { name: "x", slug: "x" }`
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`
- **AND** no row is inserted in `projects`
- **AND** no capability rows are minted

### Requirement: `Operation.PLATFORM_ADMIN` and `ResourceType.PLATFORM` are added to the authz primitives

The system SHALL extend `Operation` with `PLATFORM_ADMIN = "platform_admin"` and `ResourceType` with `PLATFORM = "platform"`. These SHALL NOT appear in any role bundle template; they are reserved for the platform-staff path.

#### Scenario: PLATFORM_ADMIN exists on Operation

- **WHEN** code imports `Operation.PLATFORM_ADMIN`
- **THEN** the value is `"platform_admin"`

#### Scenario: No bundle declares PLATFORM_ADMIN

- **WHEN** the bundle catalogue is enumerated
- **THEN** zero `CapabilityTemplate` entries have `operation = Operation.PLATFORM_ADMIN`

### Requirement: `can()` checks the staff flag for platform-level resources

The system SHALL extend `can()` so that a check for `(Operation.PLATFORM_ADMIN, ResourceType.PLATFORM, resource_id?)` returns True iff the actor's `actors.is_platform_staff` column is TRUE. The check SHALL NOT consult the `capabilities` table for this combination.

#### Scenario: Staff passes the platform check

- **GIVEN** an actor with `is_platform_staff = TRUE` and zero capability rows
- **WHEN** `can(actor.id, Operation.PLATFORM_ADMIN, ResourceType.PLATFORM)` is called
- **THEN** the result is True

#### Scenario: Non-staff fails the platform check

- **GIVEN** an actor with `is_platform_staff = FALSE` and `role:owner` over an org
- **WHEN** `can(actor.id, Operation.PLATFORM_ADMIN, ResourceType.PLATFORM)` is called
- **THEN** the result is False

#### Scenario: Org-level checks are unaffected

- **GIVEN** an actor with org bundles but `is_platform_staff = FALSE`
- **WHEN** `can(actor.id, Operation.READ, ResourceType.ORGANISATION, org.id)` is called
- **THEN** the existing capabilities-table evaluation runs and returns the same result it always did

