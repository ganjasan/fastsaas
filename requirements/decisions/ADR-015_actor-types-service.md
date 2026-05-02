---
tags: [decision, status/accepted, category/data-model, priority/high]
created: 2026-05-01
decided: 2026-05-01
amends: ["ADR-009_actor-model-cti"]
traces_to:
  related:
    - "[[ADR-009_actor-model-cti]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  use_cases:
    - "UC-005 (bulk pipeline service)"
    - "UC-007 (org-level service account)"
  spike: platform-saas-core-architecture-spike
  epic: ganjasan/fastsaas (Identity & Access epic; issue TBD)
---

# ADR-015: Actor types — add SERVICE alongside HUMAN and AGENT

## Status
Accepted

## Context

Round 1 ADR-009 established two actor types — HUMAN and AGENT — with the invariant that AGENT must have a `parent_actor_id` pointing at a HUMAN. This expressed personal AI assistants well (Claude Code, Cursor; UC-003).

UC-005 and UC-007 surfaced a different shape: an org-owned automation account (cron, CI, internal pipelines, integration bots). It has no meaningful HUMAN parent — the responsible HUMAN may leave the company, but the service must keep running. Forcing a designated-HUMAN parent means the service's lifecycle is tied to a person who shouldn't be load-bearing.

## Decision

**Add `SERVICE` as a third `actor_type`. SERVICE is org-owned, has an `owner_actor_id` for accountability (notifications, billing attribution), but `parent_actor_id IS NULL` so its lifecycle is independent of any HUMAN.**

### Schema additions

```sql
-- Update actors check constraint (amends ADR-009)
ALTER TABLE actors
  DROP CONSTRAINT actor_type_valid,
  ADD CONSTRAINT actor_type_valid CHECK (actor_type IN ('HUMAN','AGENT','SERVICE'));

-- New invariant for SERVICE
ALTER TABLE actors
  ADD CONSTRAINT service_no_parent
  CHECK (actor_type <> 'SERVICE' OR parent_actor_id IS NULL);

-- New child table (per ADR-009 CTI pattern)
CREATE TABLE services (
  actor_id          UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
  organisation_id   UUID NOT NULL REFERENCES organisations(id),
  owner_actor_id    UUID NOT NULL REFERENCES actors(id),    -- responsible HUMAN (notifications, billing)
  description       TEXT,
  last_used_at      TIMESTAMPTZ NULL
);
```

API keys for SERVICE come from the `api_keys` table per ADR-017 (not embedded here — supports multiple keys, per-key scope).

### Constraints

- SERVICE has **no UI login** — only API key authentication (per ADR-017).
- SERVICE **cannot hold admin-level capabilities** (`admin:org`, `delete:org`) — enforced as a default org policy (per ADR-016). Operational scope only.
- SERVICE is **deletable independently** of `owner_actor_id`; deleting the owner does NOT cascade to SERVICE (ownership is reassigned to org admin or another HUMAN).
- SERVICE in `audit_log` is shown distinctly via `services.description`, not via the owner HUMAN's display_name.

### Owner-vs-parent distinction

This is the key design difference from AGENT:

| | AGENT | SERVICE |
|--|--------|---------|
| `parent_actor_id` | HUMAN (required) | NULL (forbidden) |
| `owner_actor_id` (in child table) | n/a | HUMAN (required) — accountability only, not lifecycle |
| Cascade on owner soft-delete | AGENT cascade soft-deletes | SERVICE survives; ownership re-assigned |
| Authentication | API key (ADR-017) | API key (ADR-017) |
| UI login | No | No |
| Audit display | "via AGENT (parent: <HUMAN>)" | "via SERVICE: <description>" |

## Alternatives Considered

### Designated HUMAN as parent (workaround keeping ADR-009 intact)

Make a "system user" HUMAN, parent all SERVICEs to it. Rejected: pollutes audit attribution ("who did this?" → "system user, but actually nobody"), couples lifecycles unnecessarily, and is opaque to anyone reading the schema later.

### Allow `parent_actor_id` to optionally be NULL on AGENT (relax existing constraint)

Conflates AGENT and SERVICE conceptually. Rejected — they have meaningfully different lifecycles and audit-display needs.

### Multiple new types (SERVICE, BOT, INTEGRATION, …)

Premature differentiation. Rejected — one new type covers UC-005, UC-007; subdivide later if a real distinction emerges.

## Consequences

### Positive

- UC-005 and UC-007 satisfied as first-class flows.
- Audit attribution is honest — no fake "system user" muddying the trail.
- Lifecycle independence: SERVICE survives organisational churn.
- Default policy that SERVICE cannot hold `admin:*` provides a safety floor.
- Future actor types (e.g. external partner integration) can join the same CHECK without further model changes.

### Negative

- Adds one more conditional in code that distinguishes actor types. Mitigated by `Actor.is_service` / `is_agent` / `is_human` properties.
- Migration: existing `agents.api_key_hash` is removed (per ADR-017); SERVICE never had any apiariation in production yet, so no data migration today.

## Open Questions

- Can SERVICE create its own AGENTs (sub-services)? *Rejected for v1: parent chain depth = 1. Revisit if needed.*
- Org-level limit on number of SERVICEs (anti-sprawl): Phase 2 enforcement; schema supports.
- SERVICE-to-SERVICE handoff (one service triggers another): same audit pattern as HUMAN-to-AGENT, no special mechanism needed.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #13]]
- [[../formal/use-cases/UC-005_bulk-pipeline-service]]
- [[../formal/use-cases/UC-007_org-level-service-account]]
- [[ADR-009_actor-model-cti]] — original CTI model; this ADR amends the type set
- [[ADR-013_authorization-capabilities-role-bundles]] — capabilities bound to SERVICE
- [[ADR-016_org-policy-mechanism]] — default policy enforcing SERVICE scope ceiling
- [[ADR-017_api-keys]] — authentication for SERVICE
