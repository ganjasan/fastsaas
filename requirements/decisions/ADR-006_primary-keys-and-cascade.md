---
tags: [decision, status/accepted, category/data-model, priority/high]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-003_ontology-and-data-flow]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-006: Primary keys and cascade strategy

## Status
Accepted

## Context

Every table in `platform` needs a primary-key strategy and a deletion semantics. The choice is foundational: it dictates URL shape (`/orgs/47` vs `/orgs/01HQ…`), index behaviour at scale, JOIN performance, and how compliance-critical data (audit log) survives org lifecycle events.

Two intertwined questions:

1. **PK type:** serial bigint, UUID v4, UUID v7, ULID?
2. **Cascade strategy:** what happens to dependent rows (and to the audit log) when an organisation, project, or actor is removed?

This decision will be inherited by the future FASTSAAS-specific 5-level hierarchy (Portfolio → Asset → Analysis → Scenario) in epic [#2](https://github.com/FASTSAAS/fastsaas/issues/2), so consistency matters.

## Decision

### PK type: UUID v7 generated in Python

- All tables use `id UUID PRIMARY KEY` populated with **UUID v7** (RFC 9562, time-ordered).
- Generated in the Python application layer (e.g. `uuid_utils.uuid7()`); no Postgres extension required, so the schema works on any managed Postgres (RDS, Supabase, Neon).

### Cascade strategy: soft-delete domain, immortal audit

- **Domain tables** (`organisations`, `projects`, `actors`, `users`, `agents`, memberships, settings) carry `deleted_at TIMESTAMP NULL`. Standard queries filter `WHERE deleted_at IS NULL`. Hard delete is reserved for admin tooling and GDPR right-to-erasure.
- **`audit_log` and any compliance-related table:** never deleted. The FK to `organisations.id` is **nullable, no `ON DELETE` clause**. Even on a hard org-delete the audit row survives with the FK becoming an orphan reference — acceptable for a log.

The same pattern applies to all future tables added under this codebase, including the eventual FASTSAAS 5-level hierarchy.

## Alternatives Considered

### Serial bigint everywhere

- Smallest storage footprint (8 bytes vs 16) and shortest URLs (`/orgs/47`).
- **Rejected:** leaks tenant cardinality. `/orgs/47` reveals you have ≤ 47 orgs; an attacker can enumerate by incrementing.

### UUID v4 everywhere

- Random, opaque — no enumeration leak.
- **Rejected:** poor B-tree behaviour. Inserts into a UUID v4-keyed table fragment the index; performance degrades visibly past a few million rows.

### ULID

- Time-ordered like UUID v7, base-32 (shorter URL representation: `01HQ8KZJ8X8000P0V7QNH3CWAD`).
- **Rejected:** not a native Postgres type; would need a custom type or string column. UUID v7 is now standardised (RFC 9562, May 2024) and has wide tooling support.

### Hard delete with `ON DELETE CASCADE`

- Truly "delete" — no rows linger.
- **Rejected:** would erase the audit trail of the deleted org, breaking compliance use cases (industry-specific compliance / SOC-2 / GDPR proof-of-action).

### Hard delete with `ON DELETE RESTRICT`

- Org cannot be deleted while audit rows exist (i.e., never).
- **Rejected:** in practice no one ever deletes an org; the soft-delete + immortal audit pattern is more honest about the lifecycle.

## Consequences

### Positive

- Tenant cardinality is not leaked through IDs.
- Time-ordered UUID v7 keeps B-tree indexes healthy at scale (within ~0.5–1× the performance of serial keys for typical workloads).
- Audit immortality satisfies compliance without a special "frozen" flag or separate cold storage.
- Schema is portable across any Postgres deployment (no extensions needed).
- Future FASTSAAS 5-level hierarchy (epic #2) inherits the same scheme cleanly.

### Negative

- 16-byte PK vs 8-byte serial — modest storage impact at SaaS scale.
- Soft-delete must be applied consistently in queries (forgetting filter = data leakage of "deleted" rows). Mitigated by SQLModel mixin / RLS policy enforcement (see ADR-007).
- Two INSERTs to create `actors` + child row (per ADR-009 CTI) — wrapped in a transaction.

## Open Questions

- Internal `_pk SERIAL` for JOIN performance — deferred until profiling shows pain. Not adopted upfront.
- Periodic anonymisation of `intent_metadata` PII inside surviving audit rows for GDPR right-to-erasure — to be designed as a follow-up backlog item.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #2]]
- [[ADR-007_multi-tenant-isolation]]
- [[ADR-010_audit-log-shape]]
- RFC 9562 (UUID v7 spec) — https://www.rfc-editor.org/rfc/rfc9562
- `uuid_utils` (Python UUID v7 lib) — https://github.com/aminalaee/uuid-utils
