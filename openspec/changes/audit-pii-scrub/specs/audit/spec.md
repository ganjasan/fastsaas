## ADDED Requirements

### Requirement: Audit log PII fields are scrubbable via a sanctioned endpoint

The system SHALL provide an endpoint `POST /api/orgs/{slug}/audit/scrub` that, gated on `Operation.SCRUB` over `ResourceType.AUDIT_LOG` for the target org, replaces `intent_metadata.{ip, user_agent, original_prompt, path}` with the literal string `"<scrubbed:gdpr>"` for `audit_log` rows matching the supplied filter. The structural columns (`entity_type`, `entity_id`, `action`, `actor_id`, `organisation_id`, `timestamp`, `intent_hash`, `diff`) SHALL NOT be modified by this endpoint.

#### Scenario: DPO scrubs by actor_id and produces matching count

- **GIVEN** an org `acme` with three audit rows for actor `A` carrying populated `intent_metadata.ip` and `intent_metadata.user_agent`
- **AND** an actor `D` with the `role:dpo` bundle on `acme` (granting `read + scrub` on `audit_log`)
- **WHEN** `D` calls `POST /api/orgs/acme/audit/scrub` with body `{"filter": {"actor_id": "<A>"}}`
- **THEN** the response is HTTP 200 with `{"rows_scrubbed": 3, "dry_run": false}`
- **AND** every matched row's `intent_metadata.ip` and `intent_metadata.user_agent` and `intent_metadata.original_prompt` (if present) and `intent_metadata.path` equal the literal `"<scrubbed:gdpr>"`
- **AND** the matched rows' `entity_type`, `entity_id`, `action`, `actor_id`, `organisation_id`, `timestamp`, `intent_hash`, and `diff` are unchanged byte-for-byte from before the call

#### Scenario: Compliance officer cannot scrub

- **GIVEN** an actor with `role:compliance_officer` on `acme` (read-only on `audit_log`)
- **WHEN** the actor calls `POST /api/orgs/acme/audit/scrub` with a valid filter
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`
- **AND** zero `audit_log` rows are modified

#### Scenario: Member without DPO bundle cannot scrub

- **GIVEN** an actor with `role:member` on `acme`
- **WHEN** the actor calls `POST /api/orgs/acme/audit/scrub` with a valid filter
- **THEN** the response is HTTP 403 with `code = "authz.forbidden"`

### Requirement: Scrub endpoint supports dry-run mode that mutates nothing

The system SHALL accept a `dry_run: true` flag in the scrub request body. In dry-run mode the endpoint SHALL return the count of rows that would be scrubbed by the filter without modifying any `audit_log` rows AND without writing a meta-audit row.

#### Scenario: Dry-run returns count without mutating

- **GIVEN** an org `acme` with five audit rows for actor `A`
- **WHEN** a DPO calls the scrub endpoint with `{"filter": {"actor_id": "<A>"}, "dry_run": true}`
- **THEN** the response is HTTP 200 with `{"rows_scrubbed": 5, "dry_run": true}`
- **AND** all five rows' `intent_metadata` is unchanged byte-for-byte
- **AND** no row with `entity_type = "audit_scrub"` is appended to `audit_log` for this call

### Requirement: Every wet (non-dry-run) scrub call writes one meta-audit row

The system SHALL write exactly one `audit_log` row per wet scrub call, in the same migrator transaction as the scrub UPDATE, with `entity_type = "audit_scrub"`, `action = "scrub"`, `entity_id = <uuid4>`, `actor_id = <the DPO>`, `organisation_id = <target org>`, and `diff = {"filter": {...}, "rows_scrubbed": N}`. If the scrub UPDATE fails, the meta-audit row SHALL roll back with it.

#### Scenario: Wet scrub appends one audit_scrub row

- **WHEN** a DPO performs a wet scrub matching three rows
- **THEN** exactly one new row exists in `audit_log` with `entity_type = "audit_scrub"`, `action = "scrub"`, `actor_id = <DPO>`, `diff.rows_scrubbed = 3`, and `diff.filter` echoing the request filter

#### Scenario: Re-running the same scrub is a no-op for data but logs the intent

- **GIVEN** a scrub has already been performed for filter `F`, leaving zero un-scrubbed rows
- **WHEN** the DPO re-runs the scrub with the same filter `F`
- **THEN** the response is HTTP 200 with `{"rows_scrubbed": 0, "dry_run": false}`
- **AND** a new `audit_scrub` meta row is appended (the DPO's repeat intent is itself logged)
- **AND** no `audit_log` row's `intent_metadata` is modified by the rerun

### Requirement: Scrub filter rejects empty bodies and unknown keys

The system SHALL require at least one of `actor_id`, `ip`, `since`, `until` in the filter. The system SHALL reject any request whose `filter` object contains an unknown key.

#### Scenario: Empty filter is rejected

- **WHEN** a DPO calls the scrub endpoint with `{"filter": {}}` or with no `filter` at all
- **THEN** the response is HTTP 400 with `code = "audit.scrub.empty_filter"`
- **AND** no `audit_log` row is modified

#### Scenario: Unknown filter key is rejected

- **WHEN** a DPO calls the scrub endpoint with `{"filter": {"actor_id": "<A>", "country": "DE"}}`
- **THEN** the response is HTTP 400 with `code = "audit.scrub.unknown_filter_key"`
- **AND** no `audit_log` row is modified

### Requirement: New `Operation.SCRUB` capability and `role:dpo` bundle

The system SHALL add `Operation.SCRUB = "scrub"` to the `Operation` enum and a `role:dpo` bundle to `BUNDLES` containing exactly `[Cap("read", "audit_log", scope="self"), Cap("scrub", "audit_log", scope="self")]`. The bundle SHALL be a primary bundle (one per actor per org).

#### Scenario: role:dpo bundle has read and scrub on audit_log

- **WHEN** a `role:owner` mints `role:dpo` for actor `D` on org `acme` via `authz.service.mint_bundle`
- **THEN** `D` has exactly two capability rows: `(read, audit_log, acme)` and `(scrub, audit_log, acme)`, both tagged with `bundle_name = "role:dpo"`

#### Scenario: role:dpo replaces a prior primary bundle

- **GIVEN** actor `D` already has `role:member` on `acme`
- **WHEN** `role:dpo` is minted for `D` on `acme`
- **THEN** the prior `role:member` capabilities are revoked (per the existing primary-bundle replacement rule from PR #11)
- **AND** the org's denormalised `organisation_members.role` for `D` is updated to `"role:dpo"`

### Requirement: Scrub is org-scoped and refuses cross-org filters

The system SHALL execute the scrub UPDATE scoped to `organisation_id = <slug-resolved org id>` regardless of filter values. A request whose URL slug does not match the actor's org membership for the actor performing the scrub SHALL be rejected by the existing tenant-context middleware before the capability check runs.

#### Scenario: DPO of acme cannot scrub globex rows

- **GIVEN** orgs `acme` and `globex` each have audit rows for actor `A` (member of both)
- **AND** actor `D` is a DPO on `acme` only
- **WHEN** `D` calls `POST /api/orgs/acme/audit/scrub` with `{"filter": {"actor_id": "<A>"}}`
- **THEN** only `acme`'s rows for `A` are scrubbed
- **AND** `globex`'s rows for `A` are unchanged
