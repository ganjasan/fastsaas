---
tags: [decision, status/accepted, category/data-model, priority/high]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-006_primary-keys-and-cascade]]"
 - "[[ADR-007_multi-tenant-isolation]]"
 - "[[ADR-009_actor-model-cti]]"
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

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #7]]
- [[ADR-006_primary-keys-and-cascade]]
- [[ADR-007_multi-tenant-isolation]]
- [[ADR-009_actor-model-cti]]
