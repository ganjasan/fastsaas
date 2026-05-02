---
tags: [decision, status/accepted, category/security, priority/critical]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
  related:
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-009_actor-model-cti]]"
    - "[[ADR-015_actor-types-service]]"
    - "[[ADR-016_org-policy-mechanism]]"
    - "[[ADR-017_api-keys]]"
  research:
    - "[[../reference/access-model-rbac-vs-capability]]"
  use_cases:
    - "UC-001 (per-project guest)"
    - "UC-003 (AGENT bounded scope)"
    - "UC-005 (SERVICE scope)"
    - "UC-007 (SERVICE actor)"
    - "UC-010 (org policy on capabilities)"
  spike: platform-saas-core-architecture-spike
  epic: ganjasan/fastsaas (Identity & Access epic; issue TBD)
---

# ADR-013: Authorization model — capability-based with role bundles

## Status
Accepted

## Context

Round 1 of the SaaS-core spike spoke vaguely of "owner / admin / member / viewer" roles without committing to an enforcement mechanism. Round 2 surfaced use cases that exposed the gap:

- **UC-001** — external client of a Practitioner is *not* a member of the Practitioner's org; needs **per-project access** without org-membership.
- **UC-003** — AGENT acts on behalf of HUMAN with a *bounded* subset of HUMAN's authority — pure roles cannot express attenuation.
- **UC-005, UC-007** — SERVICE actor receives operational scope, not a "role" in any human sense.
- **UC-010** — org-wide policy expressed as constraints on *capabilities*, not roles.

A separate research note (`requirements/reference/access-model-rbac-vs-capability.md`) compared pure RBAC, capability-based, and hybrid against all UCs and against industry analogues (AWS IAM, GCP IAM, GitHub, Linear, Vault, K8s RBAC). All production-grade IAM systems have converged on a hybrid: capability-based primitives with named bundles for ergonomics.

## Decision

**Hybrid authorization — capabilities as the single underlying primitive; role bundles as the presentation layer for admins and the UX for "assign user X as admin".**

### Mechanics

**1. The `capabilities` table is the only enforcement source.**

```sql
CREATE TABLE capabilities (
  id              UUID PRIMARY KEY,                       -- UUID v7 per ADR-006
  actor_id        UUID NOT NULL REFERENCES actors(id),
  operation       TEXT NOT NULL,                          -- 'read' | 'write' | 'delete' | 'run' | 'admin' | 'share' | 'grant'
  resource_type   TEXT NOT NULL,                          -- 'organisation' | 'project' | 'scenario' | 'audit_log' | 'agent' | 'service'
  resource_id     UUID NULL,                              -- specific UUID or NULL for type-wide grant
  conditions      JSONB DEFAULT '{}',                     -- {ip_allowlist, time_window, ...}
  bundle_name     TEXT NULL,                              -- 'role:admin' | 'role:guest_viewer' | NULL for one-off
  granted_by      UUID REFERENCES actors(id),
  granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at      TIMESTAMPTZ NULL,
  revoked_at      TIMESTAMPTZ NULL,
  policy_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
  metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_cap_lookup
  ON capabilities (actor_id, operation, resource_type, resource_id)
  WHERE revoked_at IS NULL AND policy_blocked = FALSE;

CREATE INDEX idx_cap_bundle
  ON capabilities (actor_id, bundle_name)
  WHERE revoked_at IS NULL;
```

**2. A capability check `can(actor, operation, resource)` is the only authorization API**, returning boolean. Application code uses it; route dependencies wrap it. RLS (per ADR-007) remains the database-side guarantee; capability is the application-side gate.

**3. Default role bundles — defined in code, not a DB table** (rare changes, easier to review):

| Bundle | Capabilities |
|--------|--------------|
| `role:owner` | admin on org, admin on all projects, share, read audit |
| `role:admin` | admin on projects, share, read audit |
| `role:member` | read org, write/run on projects |
| `role:viewer` | read org, read projects |
| `role:guest_viewer` | read on a specific project (resource_id required) |
| `role:compliance_officer` | read audit_log across org (no operational data) |

**4. Provisioning.** Assigning a role mints all capabilities in its bundle, tagging each with `bundle_name`. Changing role revokes the old bundle and mints the new. One-off grants (UC-001 guest, UC-003 AGENT scope) mint capabilities directly without a bundle (or with an appropriate bundle for UI display).

**5. Policy hooks.** Capability provisioning consults org policies (per ADR-016) and may block creation; runtime checks consult the same policies and reject if the capability is `policy_blocked`.

**6. Audit.** Every capability use writes an audit row (per ADR-010) with `intent_metadata.capability_id` referencing the capability that authorised the action.

### Operation vocabulary (locked for v1)

`read`, `write`, `delete`, `run` (model execution), `admin` (settings, schema, lifecycle), `share` (grant capabilities to others within a resource), `grant` (mint capabilities for AGENTs / SERVICEs you own).

### Resource types (locked for v1)

`organisation`, `project`, `scenario`, `audit_log`, `agent`, `service`. Wildcard `*` reserved for system roles only.

## Alternatives Considered

### Pure RBAC + per-resource ACL on top

The conventional SaaS approach. Rejected because two parallel mechanisms (roles for "standard" cases, ACLs for sharing) duplicate the enforcement surface, the audit story, and the UI; and the AGENT scope problem (UC-003) doesn't fit either cleanly.

### Pure capability-based (no role bundles)

Theoretically cleaner; admin UX suffers ("create user, then mint 7 capabilities each time"). Rejected — bundle = template, ideologically identical to pure capability with much better UX.

### ACL only (resource → permitted actors)

Loses actor-centric audit ("what could actor X have done?" requires joining ACLs of every resource). Rejected.

### Attribute-Based Access Control (ABAC)

Maximum generality (rules like "if user.dept = project.dept and user.clearance ≥ project.required …"). Rules are hard to debug, performance-sensitive, and our set of attributes is too small to justify the abstraction. Rejected.

## Consequences

### Positive

- All 8 use cases (UC-001..UC-010) map naturally to capabilities.
- Sharing = mint a capability; revocation = update one row; expiry = `expires_at`.
- AGENT scope is a strict subset of HUMAN's capabilities — natural intersection (no special "attenuated role" mechanism).
- Compliance audit query "show all admins" is just `WHERE bundle_name = 'role:admin'` — same ergonomics as pure RBAC.
- Industry-aligned: AWS IAM, GCP IAM, GitHub, Linear, Vault, K8s all converge on this hybrid.

### Negative

- More rows than RBAC (a million users × tens of capabilities each). Mitigated by indexes + Redis cache of materialised role bundles per actor.
- Every request runs a capability lookup. Sub-millisecond with index; 5–10 ms cache miss; acceptable for our scale.
- Discipline required: do not bypass `can(...)` and query the capabilities table directly. Lint and code review.

## Open Questions

- Custom role bundles per org (admin defines own bundle): defer to Phase 2 — start with the 8 default bundles.
- Bundle revision: when default bundles evolve (new operation added), how do existing capabilities upgrade? Migration script per change. Captured in `requirements/open-questions/` post-merge.
- UI: capability-detail view (advanced) vs role-only view (default) — Phase 2 admin design-system epic (#18) is the natural home.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #11]]
- [[../reference/access-model-rbac-vs-capability]] — full comparative analysis
- AWS IAM — https://docs.aws.amazon.com/IAM/latest/UserGuide/intro-structure.html
- HashiCorp Vault policies — https://developer.hashicorp.com/vault/docs/concepts/policies
- Object-capability model background — https://en.wikipedia.org/wiki/Capability-based_security
