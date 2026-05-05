# Tasks — audit-pii-scrub

Linked issue: ganjasan/fastsaas#13.

## 1. Capability + bundle plumbing

- [x] 1.1 Extend `Operation` enum in `backend/src/fastsaas/authz/bundles.py`: add `SCRUB = "scrub"`.
- [x] 1.2 Add `role:dpo` bundle to `BUNDLES`: `[Cap("read", "audit_log", scope="self"), Cap("scrub", "audit_log", scope="self")]`.
- [x] 1.3 Add `"role:dpo"` to `PRIMARY_BUNDLES` (one DPO per actor per org).
- [x] 1.4 Extend `OrganisationRole` StrEnum with `DPO = "dpo"` + `_INVITE_ROLES` allow-set in `tenants/service.py`. DB CHECK constraints on `org_invitations.role`, `organisation_members.role`, `capabilities.operation`, and `audit_log.action` extended via migration `0007_org_invitations_dpo_role.py` (renamed from "just invitations" — covers all four constraints touched by this change).

## 2. Service + route

- [x] 2.1 Created `backend/src/fastsaas/audit/scrub.py` with `class AuditScrubService` and `async def scrub(*, org_id, dpo, scrub_filter, dry_run)`. Wet path opens `migrator_session_scope`, runs `UPDATE audit_log SET intent_metadata = jsonb_set(...)` with `create_missing => false` per field, captures `rowcount`, calls `audit.record(db, action="scrub", entity_type="audit_scrub", ...)` in the same transaction. Dry path: `SELECT count(*)` over the same `WHERE`, no UPDATE, no meta row.
- [x] 2.2 `ScrubFilter` Pydantic model with `extra="forbid"` and `is_empty()` helper. Empty-filter check happens in route + service-layer (defence in depth).
- [x] 2.3 `ScrubResult` Pydantic model: `{rows_scrubbed: int, dry_run: bool}`.
- [x] 2.4 Route `POST /orgs/{slug}/audit/scrub` in `backend/src/fastsaas/api/audit.py`. Resolves `TenantContextDep`, calls `can(actor, SCRUB, AUDIT_LOG, ctx.org.id, db, redis)` — 403 `authz.forbidden` on miss. Maps `ValidationError` → 400 `audit.scrub.unknown_filter_key`/`audit.scrub.invalid_filter`; `ScrubFilterError` → 400 with the error's `code` attribute.
- [x] 2.5 Wired `audit_router` into `main.py`.
- [x] 2.6 Extended `AuditAction` Literal in `audit/service.py` to include `"scrub"` (the meta-audit row's action).

## 3. Sentinel + redaction integration

- [x] 3.1 `SCRUBBED_GDPR_LITERAL = "<scrubbed:gdpr>"` in `audit/scrub.py`; re-exported from `audit/__init__.py` along with `AuditScrubService`, `ScrubFilter`, `ScrubFilterError`, `ScrubRequest`, `ScrubResult`, `SCRUBBED_FIELDS`.
- [x] 3.2 The scrub UPDATE replaces ONLY `ip`, `user_agent`, `original_prompt`, `path` via four chained `jsonb_set(..., create_missing => false)` calls — absent keys stay absent (presence-of-key is preserved).
- [x] 3.3 `PII_INTENT_KEYS` constant added to `audit/intent.py`; `audit/scrub.py` imports it and module-level asserts `tuple(SCRUBBED_FIELDS) == PII_INTENT_KEYS`. If `intent.py` adds a new client-controlled key without extending the scrub set, the assert fires at import time in dev/test.

## 4. Wiegers documentation

- [x] 4.1 Appended "2026-05-05 — PII scrub contract for GDPR Art.17 right-to-erasure" to `requirements/decisions/ADR-010_audit-log-shape.md`. Documents sentinel discriminator from `<redacted>`, org-scoped four-field-only mutation rule, meta-audit row contract, capability/bundle split, `actor_id` non-scrubbability, and the DPO's-own-metadata-not-scrubbed rule.
- [x] 4.2 Created `requirements/formal/stakeholders/SH-data-protection-officer.md` (Wiegers form): goals, authority/responsibilities (read+scrub but not operational mutation), tasks, success metrics, pain points (real-rep not engaged, `actor_id` non-scrubbability, coverage drift, retention vs subject scrub), constraints, questions for next interview. Sibling profile to `SH-compliance-officer`. Pinned `draft`.
- [x] 4.3 Updated ADR-010 frontmatter: `amended: 2026-05-05`, added DPO profile to `stakeholders`, added this change + the archived audit-trail-middleware path to `changes`.

## 5. Documentation for Claude

- [x] 5.1 Updated `backend/src/fastsaas/audit/CLAUDE.md` §"What NOT to do" — the `audit_log` immortality bullet now points to the new §"Scrubbing PII for GDPR" section instead of "(backlog)".
- [x] 5.2 New §"Scrubbing PII for GDPR" section in `audit/CLAUDE.md`: PII key list (canonical in `intent.py::PII_INTENT_KEYS`), curl-recipe wet scrub, server-side flow, what the scrub never touches, filter rules, idempotency, sentinel discriminator.

## 6. Tests

- [x] 6.1 Unit — `tests/test_audit_scrub.py` covers `ScrubFilter` validation (empty + unknown-key reject), `ScrubRequest.dry_run` default, sentinel discriminator from `<redacted>`, and the `SCRUBBED_FIELDS == PII_INTENT_KEYS` invariant.
- [x] 6.1a Bundle catalogue tests in `tests/test_authz_bundles.py`: `role:dpo` carries exactly read+scrub on `audit_log`; `role:compliance_officer` does NOT carry scrub; `Operation.SCRUB` is granted by exactly one bundle (no creep).
- [x] 6.3 Integration — `tests/test_audit_scrub_integration.py::test_dpo_scrubs_by_actor_id_only_touches_pii_keys`: DPO scrubs by actor_id, structural columns (entity_type/entity_id/action/intent_hash/diff/organisation_id) unchanged byte-for-byte; PII keys (when present) replaced with sentinel.
- [x] 6.4 Integration — `test_compliance_officer_cannot_scrub`: 403 + no audit_scrub rows + total row count unchanged.
- [x] 6.5 Integration — `test_plain_member_cannot_scrub`: 403.
- [x] 6.6 Integration — `test_wet_scrub_appends_meta_audit_row`: exactly one `audit_scrub` row with action="scrub", filter echoed in `diff.after.filter`, `rows_scrubbed` echoed in `diff.after.rows_scrubbed`. The DPO's own intent_metadata is NOT scrubbed (legitimate-interest carve-out).
- [x] 6.7 Integration — `test_rerun_returns_zero_but_logs_meta`: second run returns `rows_scrubbed: 0`, second `audit_scrub` row appears.
- [x] 6.8 Integration — `test_dpo_of_acme_cannot_scrub_globex`: DPO on acme scrubbing under `/orgs/acme/...` does not mutate any globex row; acme rows do contain the sentinel afterwards.
- [x] 6.9 Integration — `test_dry_run_returns_count_without_mutating_or_meta`: dry-run leaves all `intent_metadata` and the audit_scrub row count unchanged.
- [x] 6.10 Integration — `test_scrubbed_rows_remain_visible_under_compliance_officer_role`: under the `app.role = 'compliance_officer'` GUC, the scrubbed rows are still readable; at least one carries the sentinel.

(Tasks 6.2 — separate dry-run unit test with mocked execute — collapsed into 6.9's integration test, which exercises the same path through the live ASGI app and is authoritative.)

## 7. Validation + close-out

- [x] 7.1 `openspec validate audit-pii-scrub --strict` passes.
- [x] 7.2 `cd backend && uv run ruff check .` clean.
- [x] 7.3 `./run_test.sh -q` green — 216 passed (190 pre-existing + 23 new bundle/scrub unit tests + 8 new scrub integration tests, minus deltas).
- [x] 7.4 PR opened, linked to issue #13 — https://github.com/ganjasan/fastsaas/pull/16 (merged via squash commit 6f189e0).
- [x] 7.5 Archive change after merge; sync delta specs to `openspec/specs/audit/`.
