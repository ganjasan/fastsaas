---
title: Audit trail middleware — tasks
linked_issue: ganjasan/fastsaas#4
---

# Tasks

## 1. Audit core module

- [x] 1.1 `backend/src/fastsaas/audit/__init__.py` — public API re-exports (`record`, `AuditedModel`, `AuditContextMiddleware`).
- [x] 1.2 `audit/models.py` — `AuditLog` SQLModel mirroring migration-0001 schema.
- [x] 1.3 `audit/context.py` — `actor_var`, `intent_var`, `IntentContext` dataclass.
- [x] 1.4 `audit/intent.py::compute_intent_hash(request)` — prefixed sources `idem:` / `agent:` / `sess:` / `req:` per spike Decision #6.
- [x] 1.5 `audit/redact.py` — `GLOBAL_REDACT` denylist + `redact(diff, *, extra: set[str])`.
- [x] 1.6 `audit/service.py::record(db, ..., action, entity_type, entity_id, diff, ...)` — explicit write API; uses contextvars for actor + intent fallbacks; runs inside the caller's transaction.
- [x] 1.7 `audit/mixin.py::AuditedModel` — base class + mapper-event listeners (`Mapper`-level + `isinstance` filter); soft-delete flip detection; `__audit_skip__` / `__audit_redact__` / `__audit_entity_type__` class attributes.
- [x] 1.8 `audit/middleware.py::AuditContextMiddleware` — sets `actor_var` + `intent_var` for request lifetime; best-effort actor resolution.
- [x] 1.9 Wire middleware in `main.py` after identity middleware.

## 2. Service-layer integration (core)

- [x] 2.1 `OrganisationService.create` → `record("create", "organisation", ...)`
- [x] 2.2 `OrganisationService.soft_delete` → `record("delete", "organisation", ...)`
- [x] 2.3 `MembershipService.invite` → `record("create", "org_invitation", ...)`
- [x] 2.4 `MembershipService.accept` → `record("create", "member", ...)` + `record("update", "org_invitation", ...)` for the consumed token
- [x] 2.5 `MembershipService.change_role` → `record("update", "member", ...)` with `diff` showing `role` transition
- [x] 2.6 `MembershipService.remove` → `record("delete", "member", ...)`
- [x] 2.7 `ProjectService.create` → `record("create", "project", ...)` (single row even though capability fan-out happens too)
- [x] 2.8 `ProjectService.update` → `record("update", "project", ...)`
- [x] 2.9 `ProjectService.soft_delete` → `record("delete", "project", ...)`
- [x] 2.10 `ProjectShareService.share` → `record("create", "share", ...)`
- [x] 2.11 `ProjectShareService.accept` → `record("update", "share", ...)` + `record("create", "capability", ...)` for the minted guest cap
- [x] 2.12 `ProjectShareService.revoke` → `record("delete", "share", ...)` + `record("update", "capability", ...)` if a consumed-cap was soft-revoked
- [x] 2.13 `authz.service.mint_bundle` / `mint_capability` / `revoke_bundle` / `revoke_capability` — emit `record(..., "capability", ...)` with action and bundle_name in metadata. Bootstrap/migration callers (no contextvar) silently skip per `_audit_context_present()` so non-request grants don't crash.

## 3. Wiegers documentation

- [x] 3.1 **Stakeholder profile** — `requirements/formal/stakeholders/SH-compliance-officer.md` (Wiegers form): goals, authority/responsibilities, tasks, success metrics, pain points, capability-creep risks, GDPR-vs-immortality conflict, downstream coverage-drift mitigation. Pinned `draft` until interviewed.
- [x] 3.2 ADR-010 amendment — append "Extension contract for downstream products" section to `requirements/decisions/ADR-010_audit-log-shape.md`:
   - `entity_type` open vocabulary + naming convention.
   - Two write paths: explicit `record(...)` and `AuditedModel` mixin.
   - `actor_var` / `intent_var` contextvars as the canonical handoff.
   - `__audit_redact__` extends global denylist, never replaces it.
   - Reference SH-compliance-officer as the consumer profile this contract serves.
- [x] 3.3 Update `traces_to:` frontmatter on ADR-010 to reference this change + the stakeholder profile.

## 4. Documentation for Claude

- [x] 4.1 **`CLAUDE.md` at repo root** — what FastSaaS is, must-not architectural rules, where-to-look map, recipes (audited table, capability-gated route, vitest, e2e), pointer to module guides.
- [x] 4.2 **`backend/src/fastsaas/audit/CLAUDE.md`** — explicit-vs-mixin decision tree, downstream entity recipe, non-CRUD recipe, redaction layering, RLS read examples, what-NOT-to-do, silent-coverage-gap failure mode.

## 5. Tests

- [x] 5.1 Unit — `audit/intent.py::compute_intent_hash` per prefix branch (`idem:`, `agent:`, `sess:`, `req:`). (`tests/test_audit_intent.py`)
- [x] 5.2 Unit — `audit/redact.py::redact` strips global + per-model keys; preserves keys as `"<redacted>"`. (`tests/test_audit_redact.py`)
- [x] 5.3 Unit — `AuditedModel` listener fires on insert / update / soft-delete-flip / restore-flip; `__audit_skip__` opts out; `__audit_redact__` merges with global; no actor context → silent skip. (`tests/test_audit_mixin.py`)
- [x] 5.4 Integration — every core mutation produces audit rows on the live ASGI app (`tests/test_audit_integration.py::test_create_org_writes_*`, `test_create_project_writes_*`).
- [x] 5.5 Integration — denylist secrets never appear non-redacted in `audit_log.diff` (`tests/test_audit_integration.py::test_audit_diff_never_contains_password_hash`).
- [x] 5.6 Integration — RLS read path: tenant scope blocks cross-org by default; `app.role = 'compliance_officer'` GUC unlocks cross-org reads. (`tests/test_audit_integration.py::test_audit_log_rls_member_only_sees_own_org`, `test_compliance_officer_role_unlocks_cross_org_audit_reads`)
- [x] 5.7 E2E — DB peek after create-org + create-project asserts the rows exist (subsumed by 5.4).

## 6. Validation + close-out

- [x] 6.1 `openspec validate audit-trail-middleware --strict` passes.
- [x] 6.2 `cd backend && uv run ruff check .` clean.
- [x] 6.3 `./run_test.sh -q` green — 190 passed (163 pre-existing + 27 new audit tests).
- [x] 6.4 PR opened, linked to issue #4 — https://github.com/ganjasan/fastsaas/pull/12.
- [x] 6.5 Archive change after merge; sync delta specs to `openspec/specs/`.
