## ADDED Requirements

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
