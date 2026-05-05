---
tags: [decision, status/accepted, category/data-model, priority/high]
created: 2026-05-01
decided: 2026-05-01
amended: 2026-05-05
supersedes: []
traces_to:
  related:
    - "[[ADR-006_primary-keys-and-cascade]]"
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-009_actor-model-cti]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  stakeholders:
    - "[[../formal/stakeholders/SH-compliance-officer]]"
    - "[[../formal/stakeholders/SH-data-protection-officer]]"
  changes:
    - openspec/changes/archive/2026-05-05-audit-trail-middleware
    - openspec/changes/audit-pii-scrub
  spike: platform-saas-core-architecture-spike
  epic: the SaaS-core epic
---

# ADR-010: Audit log shape — table with JSONB diff

## Status
Accepted

## Context

The audit trail is one of `platform`'s load-bearing features. It serves four distinct purposes:

1. **Compliance** — industry-specific compliance / SOC-2 / GDPR proofs (who, when, what changed).
2. **Debugging** — replay "why is entity X in this state" through diffs.
3. **AI-agent oversight** — group all DB mutations triggered by one AGENT prompt via `intent_hash` (per ADR's not-yet decision, captured in design.md §6).
4. **User trust** — UI activity feed for end-users.

We must lock the storage shape — flat append-only audit table vs full event sourcing — and the diff format. Retention is determined separately by the immortality rule from ADR-006.

## Decision

**Classic `audit_log` table with JSONB `{before, after}` diff. Event sourcing rejected for v1.**

### Schema

```sql
CREATE TABLE audit_log (
 id UUID PRIMARY KEY, -- UUID v7
 timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 actor_id UUID NOT NULL REFERENCES actors(id), -- FK integrity per ADR-009
 actor_type TEXT NOT NULL, -- denormalised
 parent_actor_id UUID NULL, -- denorm: AGENT initiator
 organisation_id UUID NULL, -- nullable: org-deleted survives (ADR-006)
 intent_hash TEXT NOT NULL, -- per design.md §6
 entity_type TEXT NOT NULL, -- 'project' | 'user' | 'organisation' | …
 entity_id UUID NOT NULL,
 action TEXT NOT NULL CHECK (action IN ('create','update','delete','restore')),
 diff JSONB NOT NULL, -- {"before": {...}, "after": {...}}, only changed fields
 intent_metadata JSONB NOT NULL DEFAULT '{}' -- {request_id, ip, user_agent, original_prompt,...}
);

CREATE INDEX idx_audit_org_entity_time ON audit_log (organisation_id, entity_type, entity_id, timestamp DESC);
CREATE INDEX idx_audit_intent_hash ON audit_log (intent_hash);
CREATE INDEX idx_audit_actor_time ON audit_log (actor_id, timestamp DESC);
CREATE INDEX idx_audit_timestamp ON audit_log (timestamp DESC);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_tenant_read ON audit_log
 FOR SELECT USING (organisation_id = current_setting('app.current_org', true)::uuid);
CREATE POLICY audit_write ON audit_log
 FOR INSERT WITH CHECK (true);
-- No UPDATE / DELETE policies → app role cannot mutate audit rows (immortal per ADR-006)
```

### Diff format — `{before, after}` of changed fields only

```jsonc
// create
{ "before": {}, "after": {"name": "Q4 Valuation", "owner_id": "..."} }
// update
{ "before": {"name": "Q4 Valuation"}, "after": {"name": "Q4 Valuation 2026"} }
// delete
{ "before": {"name": "Q4 Valuation 2026", /* full state */}, "after": {} }
```

Only changed fields appear; both sides are present for explicit, replay-friendly reading.

### Sensitive-field redaction

- A code-side allowlist of fields **never** written to `audit_log.diff` (`password_hash`, `api_key_hash`, OAuth secrets, etc.).
- Maintained as a constant in the audit middleware.
- New PRs that add sensitive fields must extend the list (CI lint TBD).

### Partitioning — deferred

- v1 ships an unpartitioned table.
- Add `PARTITION BY RANGE (timestamp)` (monthly) when row count crosses ~10 M. Tracked as a backlog item.

### Retention — immortal by default

Per ADR-006. GDPR right-to-erasure handled by a future endpoint that anonymises PII inside `intent_metadata` (IP, user-agent, `original_prompt`) while keeping `actor_id`, `entity_type`, `entity_id`, `action`, `intent_hash` — preserving the structural trail.

## Alternatives Considered

### Event sourcing (domain events as the source of truth)

- Full state-reconstruction from event stream; time-travel queries; cross-aggregate consistency via ordering.
- **Rejected:** solves a different problem (state reconstruction) we don't have. Adopting it forces projection design for every entity — its own spike. v1 SaaS-core would not benefit; it adds operational complexity.
- A future event-sourced subdomain (e.g. financial scenarios in epic #2) can coexist alongside `audit_log`; the two are not exclusive.

### Outbox pattern

- Solves outbound integration (publish events transactionally with state changes).
- **Rejected:** unrelated to audit — different problem.

### `{changed: {field: [old, new],...}}` diff format

- More compact storage.
- **Rejected:** the duplication of `{before, after}` is small and the read-side cost (UI diff renderer, debug REPL) is materially lower with explicit-state format.

## Consequences

### Positive

- Covers all four target use cases (compliance, debugging, AI-agent provenance, user activity feed) at the lowest implementation cost.
- Append-only + immortal table is operationally simple.
- Indexed for the common query patterns (per-entity history, per-intent grouping, per-actor activity, time-range scans).
- `JSONB diff` keeps the schema flexible; entities can evolve without audit-table migrations.

### Negative

- Replay of historical state requires reading and merging diffs in order — slow for high-mutation entities; acceptable for v1.
- Row count grows linearly with mutation volume; partitioning needed eventually (backlog).
- Field-redaction list is a discipline matter; missing an entry leaks secrets to the audit. Mitigated by allowlist + future CI lint.

## Open Questions

- Field-redaction list — write down in bootstrap (#2 in platform); CI lint a future tightening.
- Partitioning trigger threshold + ops runbook — when row count nears 10 M.
- GDPR erasure endpoint + UX — own backlog item.

## Amendments

### 2026-05-04 — Extension contract for downstream products

FastSaaS is a starter kit for downstream SaaS products (FASTSAAS-app, Apilize-style modeling tools, …). Each downstream owns its own domain tables (`scenarios`, `analyses`, `properties`, …) and must inherit audit *by convention*, never by patching core. This amendment formalises the contract every downstream relies on. Implementation lives in `openspec/changes/audit-trail-middleware`. The primary stakeholder served by this contract is [[../formal/stakeholders/SH-compliance-officer]].

#### `entity_type` is open vocabulary

`audit_log.entity_type` is `TEXT` with no DB-level CHECK constraint. Downstream picks domain names (`scenario`, `analysis`, `property`, `model_run`) without a core migration. Convention enforced by code review and `backend/src/fastsaas/audit/CLAUDE.md`:

- **lowercase, singular, noun**.
- Reserved core values: `organisation`, `project`, `member`, `share`, `org_invitation`, `capability`, `user`, `actor`. Downstream MUST NOT shadow them.

Filter queries are uniform across core and downstream — `WHERE entity_type IN ('project', 'scenario')` returns rows from both without per-domain joins.

#### Two write paths, both first-class API

The audit core ships two writers sharing the same redaction, contextvar, and transaction semantics:

1. **Explicit `await audit.record(db, *, action, entity_type, entity_id, diff, ...)`** — for non-CRUD operations (mass-revoke, capability fan-out, soft-delete-with-cascade, hand-rolled actions). Maximum control over `diff` and `intent_metadata`. Required path for any mutation that doesn't reduce to a single ORM insert/update/delete.

2. **`AuditedModel` mixin** — for typical CRUD entities. Inheritance flips on SQLAlchemy mapper-event listeners (`after_insert / after_update / after_delete`) that compute `diff` from `inspect(target).attrs.<col>.history`, apply redaction, and write the audit row in the caller's transaction. Soft-delete-flip on a `deleted_at` column is detected and reported as `action="delete"`, not `action="update"`.

The two are **complementary**, not redundant. The mixin can't see "I just revoked 47 capability rows by metadata filter"; explicit `record(...)` can't be slotted into a downstream `class Scenario(SQLModel, table=True)` without changing every CRUD function.

#### Actor + intent flow through Python `contextvars`

`audit/context.py` exposes `actor_var: ContextVar[CurrentActor | None]` and `intent_var: ContextVar[IntentContext | None]`. Both are set by `AuditContextMiddleware` at the top of every HTTP request. `record(...)` and the mapper listeners read them as defaults when the caller does not pass explicit values. This avoids threading `actor_id` and `intent_hash` through every service signature.

Asyncio-friendly by construction: `await` and `asyncio.TaskGroup` propagate contextvars correctly. `BackgroundTasks` inherits the request's contextvars at enqueue time. Workers (future `arq` epic) MUST set `actor_var` from the serialised job context before invoking the handler — the contract is documented here so the future change has a foundation to honour.

#### Sensitive-field redaction is layered

A global denylist lives in `audit/redact.py`:

```python
GLOBAL_REDACT: frozenset[str] = frozenset({
    "password_hash", "token_hash", "api_key_hash", "key_hash",
    "client_secret", "raw_token",
})
```

Downstream models extend (never replace) the denylist via the `__audit_redact__` class attribute on an `AuditedModel` subclass, or via the `extra_intent_metadata=` parameter on a `record(...)` call. Redacted keys are replaced with the literal value `"<redacted>"` so presence-of-key remains observable — useful for "did the field exist on this revision" investigations without leaking the value.

#### Failure mode — silent coverage gap

If a downstream developer ships a new SQLModel `table=True` class without inheriting from `AuditedModel` and without explicit `record(...)` calls, audit rows are silently absent — there is no compile-time signal of "you forgot audit". This is the largest ongoing risk this contract carries; mitigations:

- `backend/src/fastsaas/audit/CLAUDE.md` is the explicit guide for Claude-driven downstream work and is loaded into context for any session in this repo or its forks.
- A CI check that warns when a new `table=True` class doesn't inherit `AuditedModel` and isn't on an explicit allowlist is tracked as backlog (would close the gap mechanically).

This amendment supersedes the original "Field-redaction list — write down in bootstrap" open question; the answer is the global denylist in code plus `__audit_redact__` extension. The CI-lint open question stays open per the failure mode above.

### 2026-05-05 — PII scrub contract for GDPR Art.17 right-to-erasure

The previous amendment listed "GDPR erasure endpoint + UX" as an open question. This amendment closes the open question for the backend portion. Implementation lives in `openspec/changes/audit-pii-scrub` (issue ganjasan/fastsaas#13). The stakeholder profile is [[../formal/stakeholders/SH-data-protection-officer]] — distinct from the compliance officer who continues to read but does not erase.

#### Sentinel string and scope

The scrub replaces values inside `intent_metadata` only, never structural columns. Four keys are subject to erasure:

```python
PII_INTENT_KEYS = ("ip", "user_agent", "original_prompt", "path")
```

Replacement value is the literal string `"<scrubbed:gdpr>"` — distinct from `<redacted>` (at-write-time mask for sensitive columns) so reports can tell apart "this field was always redacted" from "this field was scrubbed post-hoc due to a subject request". The `:gdpr` discriminator leaves room for a future `<scrubbed:retention>` sentinel.

`audit/scrub.py::SCRUBBED_FIELDS` MUST equal `audit/intent.py::PII_INTENT_KEYS` — a module-level assert in `scrub.py` fails loud if the two drift. New client-controlled keys added to `intent_metadata` either join this set or are deliberately excluded with a written reason in this section.

#### What the scrub never touches

`actor_id`, `actor_type`, `parent_actor_id`, `entity_type`, `entity_id`, `action`, `organisation_id`, `timestamp`, `intent_hash`, `diff`. The structural trail is preserved; the row continues to satisfy "who did what, when" reads.

`actor_id` is an explicit non-scrubbable: a subject could in principle argue it links them to their actions, but removing it destroys the audit purpose (the join key for the structural trail). This is a bounded exception — documented and accepted under GDPR's "balance of interests" carve-out.

#### Capability and bundle

A new `Operation.SCRUB` capability gates the path; a new `role:dpo` bundle (Data Protection Officer) carries `read + scrub` on `audit_log`. `role:compliance_officer` continues to carry `read` only. Read and erase are intentionally separate responsibilities — this is the standard GDPR control split.

#### Endpoint and execution

`POST /api/orgs/{slug}/audit/scrub` (org-scoped — each org is its own GDPR controller). Body schema:

```json
{
  "filter": {"actor_id": "...", "ip": "...", "since": "...", "until": "..."},
  "dry_run": false
}
```

Filter validation:

- At least one of `actor_id`, `ip`, `since`, `until` MUST be set; empty filter rejects with 400 `audit.scrub.empty_filter`.
- Unknown keys reject with 400 `audit.scrub.unknown_filter_key`.
- Filters AND-combine — narrow scope wins on a destructive endpoint.

Wet-path (default) opens a `migrator_session_scope` (BYPASSRLS — RLS has no UPDATE policy on `audit_log` for `app_user`), runs `UPDATE audit_log SET intent_metadata = jsonb_set(...)` over rows matching `organisation_id = <slug-resolved> AND <filter> AND <not-already-scrubbed>`, and writes one meta-audit row (`entity_type="audit_scrub"`, `action="scrub"`, `diff={"filter": {...}, "rows_scrubbed": N}`) in the same transaction. If the UPDATE fails, the meta row rolls back too.

Dry-run path (`dry_run: true`) only counts; no UPDATE, no meta row.

#### Idempotency

Re-running the same filter is a no-op for data — the unscrubbed-condition excludes rows where all four PII keys already equal the sentinel. The meta-audit row still writes (the DPO's repeat intent is itself logged).

#### Meta-audit row carries the DPO's own metadata

The `audit_scrub` row's `intent_metadata` carries the DPO's request IP, user_agent, path — NOT scrubbed. The DPO acts in their professional capacity (legitimate-interest basis under GDPR), not as a data subject.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #7]]
- [[ADR-006_primary-keys-and-cascade]]
- [[ADR-007_multi-tenant-isolation]]
- [[ADR-009_actor-model-cti]]
- [[ADR-013_authorization-capabilities-role-bundles]] — `role:compliance_officer` is the primary read consumer
- [[../formal/stakeholders/SH-compliance-officer]] — stakeholder profile served by this contract
- [[../formal/stakeholders/SH-data-protection-officer]] — stakeholder profile for the PII scrub path
- `openspec/changes/audit-trail-middleware/` — implementation of the extension contract
