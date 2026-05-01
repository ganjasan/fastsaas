---
tags: [decision, status/accepted, category/security, priority/critical]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-006_primary-keys-and-cascade]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-007: Multi-tenant isolation — Postgres RLS + application-level WHERE

## Status
Accepted

## Context

`platform` is multi-tenant from day one (per AR-7 and the FE-CORE-2 multi-tenant requirement). Tenant isolation is the single highest-impact property of the system: a leak between tenants is the worst class of bug a B2B SaaS can produce, materially harder to recover from than downtime or data loss.

Two enforcement strategies exist:

- **Application-level filter** — every query passes through a service layer that injects `WHERE organisation_id = current_org`. Standard in Django, Rails.
- **Postgres Row-Level Security (RLS)** — the database itself filters rows based on a session variable; the application cannot retrieve cross-tenant data even with a buggy or missing WHERE clause.

AI-assisted development (Claude / Cursor as primary tooling) increases the risk of forgotten tenant filters, since LLMs are statistically likely to omit conditions on ad-hoc queries.

## Decision

**Both layers — RLS in the production schema as a hard guarantee, plus app-level `WHERE organisation_id = current_org` for ergonomics and explicit intent (defense-in-depth).**

### Mechanics

- Every tenant-scoped table:
 ```sql
 ALTER TABLE <name> ENABLE ROW LEVEL SECURITY;
 CREATE POLICY tenant_isolation ON <name>
 USING (organisation_id = current_setting('app.current_org', true)::uuid)
 WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid);
 ```
- A FastAPI dependency wraps each request in a transaction and runs `SET LOCAL app.current_org = '<uuid>'` before any query.
- Application code still writes explicit `WHERE organisation_id = current_org`. The RLS catches the case where the WHERE was forgotten; the explicit WHERE keeps reader intent obvious and helps the planner pick indexes.

### Postgres roles

- `app_user` — no `BYPASSRLS`. Used by the FastAPI app and arq workers.
- `alembic_migrator` — `BYPASSRLS`. Used by migrations and `pg_dump`.

### Tables exempt from RLS

- `audit_log` — its own policy (writes always allowed, reads tenant-filtered for users; admin / compliance views go through `BYPASSRLS`).
- `alembic_version`, `arq_jobs`, etc. — system tables.
- Future global / non-tenant tables (system settings, ontology references) — no RLS needed.

### Per-org theme persistence (foundation for design-system feature)

- `organisations.theme JSONB DEFAULT '{}'` — read on every request to inject the active theme into the SSR-or-CSR response. Foundation for the Phase 2 brand-customisation epic (see ADR-012).

## Alternatives Considered

### Application-level only (Django/Rails default)

- Simple, no Postgres-side complexity.
- **Rejected:** a single forgotten WHERE causes a tenant leak. AI-coding amplifies this risk class. The defense-in-depth case won.

### Postgres RLS only

- One source of truth, no double-writes.
- **Rejected:** removing the explicit WHERE makes app code less readable and less self-documenting; reviewers cannot tell at a glance whether tenant scoping was intended.

### Schema-per-tenant or DB-per-tenant

- Strongest isolation possible.
- **Rejected:** operational complexity (per-tenant migrations, connection pooling, backup orchestration) is disproportionate to current scale.

## Consequences

### Positive

- Database-enforced isolation guarantee. A bug in app code does not produce a tenant leak.
- Compliance story (industry-specific compliance / SOC-2 / GDPR) is materially stronger with "Postgres-enforced isolation" than with "we have tests."
- Explicit WHERE in code keeps intent visible to reviewers.

### Negative

- ~5–10 % query overhead from RLS evaluation; acceptable trade.
- Test ergonomics: every test fixture must `SET LOCAL` for the active tenant. Captured in a base `tenant_session` pytest fixture.
- Migrations are written under the `alembic_migrator` role; the role split must be documented and respected.
- `pg_dump` for backup uses `alembic_migrator`.
- Admin / billing reports across tenants require the `BYPASSRLS` role or a per-org loop with `SET LOCAL`.

## Open Questions

- Cross-tenant admin endpoints (billing rollup) — service role vs per-org loop. Defer to first cross-tenant feature.
- `app.current_org` is `SET LOCAL` per transaction. Verify that the asyncpg pool semantics handle this safely (LOCAL is connection-scoped, transaction lifetime). Confirmed in bootstrap (#2 in platform).

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #3]]
- [[ADR-006_primary-keys-and-cascade]]
- [[ADR-010_audit-log-shape]]
- Postgres RLS docs — https://www.postgresql.org/docs/current/ddl-rowsecurity.html
