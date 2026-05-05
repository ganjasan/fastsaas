---
title: Audit trail middleware — actor + intent_hash + diff on every mutation
status: in_progress
linked_issue: ganjasan/fastsaas#4
created: 2026-05-04
traces_to:
  adr:
    - "[[ADR-010_audit-log-shape]]"
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  spike: platform-saas-core-architecture-spike
  use_cases:
    - "UC-002 [A5] (compliance officer cross-dept audit)"
    - "UC-003 (AGENT provenance via X-Agent-Intent)"
    - "UC-008 (API key rotation auditing)"
    - "UC-010 (org policy denial auditing)"
  stakeholders:
    - "[[SH-compliance-officer]]"
---

## Why

`audit_log` table has shipped since migration `0001_initial_schema` (per ADR-010), with RLS in `0002_rls_policies` so reads are tenant-scoped and writes are append-only. **Nothing writes to it yet.** Every mutation in `orgs / projects / members / shares` (and every future downstream domain table) currently leaves no trail.

Three pressures converge here:

1. **Compliance.** SOC-2 / industry-specific frameworks expect a contiguous audit trail. The compliance-officer role (ADR-013) was wired into the read path; the write path is empty.
2. **Foundation contract.** FastSaaS is a starter kit for downstream SaaS products. Audit must be an extension primitive — downstream domains (scenarios, analyses, models, …) should pick it up by *convention*, not by patching core.
3. **Vibe-coding strategy (ADR-002).** Since downstream code is also written by Claude, the audit contract must be expressed in Claude-readable docs (CLAUDE.md, ADR amendment) so a fresh session can add a new audited entity correctly without re-reading the whole code base.

Without this change: every fix or feature ships with a compliance gap that grows with every new mutation.

## What Changes

**NEW** Audit core — `backend/src/fastsaas/audit/`:
- `models.py` — `AuditLog` SQLModel mirror of the migration-0001 schema.
- `service.py::record(...)` — explicit audit write API, called from service-layer mutations. Writes inside the caller's transaction so audit + side effect commit or roll back together.
- `mixin.py::AuditedModel` — SQLModel base class with SQLAlchemy mapper-event listeners on `after_insert / after_update / after_delete`. Auto-computes `diff` from `inspect(obj).attrs.<col>.history`, applies redaction, calls `service.record(...)` before commit.
- `intent.py::compute_intent_hash(request)` — per ADR-010 / spike Decision #6: prefixed source `idem:` / `agent:` / `sess:` / `req:`. Stored in `audit_log.intent_hash`.
- `redact.py` — global denylist (`password_hash`, `token_hash`, `api_key_hash`, OAuth secrets, …) plus per-model `__audit_redact__` opt-in extension. `redact(diff)` strips matching keys from `before` / `after` before write.
- `context.py` — `actor_var: ContextVar[CurrentActor | None]`, `intent_var: ContextVar[IntentContext | None]`. Set by middleware, read by `record(...)` and the mixin.

**NEW** FastAPI middleware — `backend/src/fastsaas/audit/middleware.py`:
- Computes `intent_hash` and `intent_metadata` (`request_id`, IP, UA, `original_prompt` from `X-Agent-Intent`) early in the request.
- Resolves `current_actor` lazily; sets `actor_var` + `intent_var` for the request lifetime.
- Wired in `main.py` after the identity middleware so `current_actor` is available.

**NEW** Service-layer integration — every existing mutation gains an `audit.record(...)` call inside its `migrator_session_scope` transaction:
- `OrganisationService.create / soft_delete`
- `MembershipService.invite / accept / change_role / remove`
- `ProjectService.create / update / soft_delete`
- `ProjectShareService.share / accept / revoke`
- `authz.service.mint_bundle / revoke_bundle / mint_capability / revoke_capability`

**UPDATE** ADR-010 — append "Extension contract for downstream" section:
- `entity_type` is an open string vocabulary (no DB CHECK). Convention: lowercase singular noun.
- Two extension styles supported: explicit `record(...)` for non-CRUD operations, `AuditedModel` mixin for typical ORM CRUD.
- Sensitive-field redaction extends via `__audit_redact__` class attribute.
- `actor_id` + `intent_hash` propagated through Python contextvars set by middleware.

**NEW** Documentation for Claude:
- **`CLAUDE.md` at repo root** — top-level brief: what FastSaaS is, the three foundation layers (identity → tenancy/authz → audit), architectural rules that must not be broken (no Department, capability is the only authz API, migrator session only in service layer, +100/+200 port shift, branch-off-main, GIVEN/WHEN/THEN tests), and a where-to-look map.
- **`backend/src/fastsaas/audit/CLAUDE.md`** — module-level guide for downstream Claude sessions: when to use explicit `record(...)` vs `AuditedModel`, how to add a new `entity_type`, how to declare `__audit_redact__`, redaction guarantees, audit-log immortality. Includes copy-paste examples for both styles.

## Out of scope (deferred)

- **Audit-log read endpoints** — list / filter / export. Compliance officers can still read via `BYPASSRLS` and a SQL client today; route-level UI is its own change once the design system (#5) lands the admin surface.
- **Idempotency cache** — per spike Decision #6, looking up `intent_hash` in Redis to short-circuit replays is deferred. We compute and store the hash from day one so the cache can be added later without a schema change.
- **GDPR right-to-erasure scrubbing** — the schema preserves `actor_id` / `entity_id` immortally; a future endpoint will redact PII inside `intent_metadata` (IP, UA, `original_prompt`) without breaking the structural trail. Backlog for post-v1.
- **Audit-driven anomaly detection** — webhook on policy-denial, capability-reuse-after-revoke, key-replay. Hooks emit; consumers ship later.
- **Partitioning of `audit_log`** — defer until row-count crosses ~10 M; documented in ADR-010.
- **`.claude/skills/audit-add-entity/`** — slash-command scaffolding for "add audited entity X with fields Y". Defer until 2–3 downstream projects have repeatedly used the same shape; writing the skill before that is premature optimisation.
