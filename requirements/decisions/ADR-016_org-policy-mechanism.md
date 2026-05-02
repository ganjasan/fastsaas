---
tags: [decision, status/accepted, category/security, priority/high]
created: 2026-05-01
decided: 2026-05-01
traces_to:
  related:
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
    - "[[ADR-015_actor-types-service]]"
    - "[[ADR-017_api-keys]]"
    - "[[ADR-010_audit-log-shape]]"
  use_cases:
    - "UC-010 (org policy on AGENT/SERVICE capabilities)"
  spike: platform-saas-core-architecture-spike
  epic: ganjasan/fastsaas (Identity & Access epic; issue TBD)
---

# ADR-016: Org policy mechanism

## Status
Accepted

## Context

Compliance-driven organisations need to set guardrails on what AGENT and SERVICE actors can do, independent of individual capability grants. Examples (from UC-010): "no AGENT may have `delete:*` capability"; "SERVICE accounts cannot write between 22:00–06:00"; "destructive operations affecting > 10 entities require HUMAN approval". Without an explicit policy mechanism, these guardrails would be hardcoded or ad-hoc.

## Decision

**Org-level policies — declarative rules applied at capability provisioning AND at runtime check, with explicit audit and a heavily-logged override flow.**

### Schema

```sql
CREATE TABLE org_policies (
  id               UUID PRIMARY KEY,                           -- UUID v7
  organisation_id  UUID NOT NULL REFERENCES organisations(id),
  name             TEXT NOT NULL,
  description      TEXT,
  rule_json        JSONB NOT NULL,                             -- structured rule (see below)
  priority         INT NOT NULL DEFAULT 100,                   -- lower = applied first
  enabled          BOOLEAN NOT NULL DEFAULT TRUE,
  created_by       UUID NOT NULL REFERENCES actors(id),
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  deleted_at       TIMESTAMPTZ NULL,
  UNIQUE (organisation_id, name)
);

CREATE TABLE org_policy_overrides (
  id               UUID PRIMARY KEY,
  policy_id        UUID NOT NULL REFERENCES org_policies(id),
  granted_by       UUID NOT NULL REFERENCES actors(id),
  reason           TEXT NOT NULL,
  expires_at       TIMESTAMPTZ NOT NULL,                       -- TTL ≤ 1 hour
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### `rule_json` structure (v1 — minimal)

```jsonc
{
  "applies_to": {                          // which actors does this policy govern
    "actor_types": ["AGENT", "SERVICE"],
    "actor_ids":   null                    // or specific actor list
  },
  "denies": {                              // what is forbidden
    "operations":     ["delete"],          // or null = any
    "resource_types": ["*"],               // or list
    "conditions":     null                 // future: time_window, threshold, etc.
  }
}
```

v1 ships with one rule type — **deny by operation × resource_type** — sufficient for the high-leverage cases (UC-010 main flow). Threshold-based and time-based rules (UC-010 [A1], [A2]) deferred to Phase 2.

### Enforcement

**At provisioning:**
- When `mint_capability(actor, op, res_type, res_id, …)` is called, the system loads applicable policies and rejects if any matches; raises `PolicyDenial` with the offending policy id.
- Already-existing capabilities that would be denied by a *new* policy are flagged `policy_blocked = TRUE` (not deleted — restorable on policy unblock or rollback).

**At runtime:**
- `can(actor, op, res)` consults capabilities AND short-circuits to `False` if any matched cap has `policy_blocked = TRUE`.
- Policy denials at runtime write a distinct audit row with `intent_metadata.policy_denial = <policy_id>` so reports show "actions denied by policy X" separately from regular permission failures.

### Override flow

- **Org owner** (only — not admin, not compliance officer) can issue a time-limited override (TTL ≤ 1 hour) for one specific policy.
- Override creation triggers: heavy audit row, Slack alert (configurable), email to all `compliance_officer` actors of the org.
- During override, capability checks bypass that policy. After expiry, normal enforcement resumes; `policy_blocked` flags re-evaluated.

### Authority matrix

| Role | Create policy | Edit policy | Delete policy | Issue override |
|------|:-:|:-:|:-:|:-:|
| `owner` | ✅ | ✅ | ✅ | ✅ |
| `admin` | ✅ | ✅ | — | — |
| `compliance_officer` | ✅ | ✅ | — | — |
| Others | — | — | — | — |

### Default policies (every new org)

Secure-by-default seeds (org admin can disable, but they exist):

| Default policy | Rule |
|----------------|------|
| `default:agent_no_admin` | AGENT cannot hold `admin:*` capability |
| `default:service_no_admin` | SERVICE cannot hold `admin:*` capability |
| `default:agent_no_org_delete` | AGENT cannot hold `delete:organisation` |
| `default:service_no_org_delete` | SERVICE cannot hold `delete:organisation` |

## Alternatives Considered

### Hardcoded constraints in application code

Simplest. Rejected — does not let orgs customise; couples policy to release cycle.

### Custom DSL (e.g. Rego, OPA-style)

Powerful, but huge ramp for v1. Rejected — `rule_json` minimal-form is enough for v1; can layer a DSL atop later without breaking schema.

### Apply policies only at runtime (skip provisioning gate)

Permits temporarily-illegal capabilities to exist; messier for audit and recovery. Rejected — gate at both layers.

### Centralised policy server (separate microservice)

Premature. Rejected for v1 — co-located with the platform.

## Consequences

### Positive

- Compliance-friendly: explicit, audit-able policy mechanism with clear authority bounds.
- Default secure: AGENT/SERVICE cannot accidentally hold dangerous capabilities even on misconfiguration.
- Safe to evolve: rule_json schema can grow new rule types (threshold, time-window) without backward-incompatible changes.
- Override flow exists but heavily friction-loaded — discourages routine use.

### Negative

- Every capability check evaluates policies — performance cost. Mitigated by Redis cache of policy set per org (5-minute TTL) + `policy_blocked` denormalised on capabilities for hot-path read.
- Default policies need migration as new actor types arrive — explicit migration step per change.
- v1 rule expressiveness is limited; threshold/time-based rules (UC-010 [A1], [A2]) deferred — communicate to early customers.

## Open Questions

- Cross-org policy templates (consultancy publishes recommended set): Phase 3.
- Policy versioning / rollback UI: data model versions implicitly via `deleted_at` + creation history; UI Phase 2.
- Policy validation tooling (dry-run on existing capabilities, count of impact): Phase 2.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #14]]
- [[../formal/use-cases/UC-010_org-policy-on-agent-scopes]]
- [[ADR-013_authorization-capabilities-role-bundles]] — what is being governed
- [[ADR-015_actor-types-service]] — SERVICE default policy ceiling
- [[ADR-017_api-keys]] — keys created under policy constraints
