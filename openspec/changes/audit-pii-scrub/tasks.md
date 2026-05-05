# Tasks — audit-pii-scrub

Linked issue: ganjasan/fastsaas#13.

## 1. Capability + bundle plumbing

- [ ] 1.1 Extend `Operation` enum in `backend/src/fastsaas/authz/bundles.py`: add `SCRUB = "scrub"`.
- [ ] 1.2 Add `role:dpo` bundle to `BUNDLES`: `[Cap("read", "audit_log", scope="self"), Cap("scrub", "audit_log", scope="self")]`.
- [ ] 1.3 Add `"role:dpo"` to `PRIMARY_BUNDLES` (one DPO per actor per org).
- [ ] 1.4 Confirm `OrganisationMember.role` enum / column accepts `"role:dpo"`. If it's a typed enum, extend it; if it's free-form text, no migration needed (the bundle naming carries it).

## 2. Service + route

- [ ] 2.1 Create `backend/src/fastsaas/audit/scrub.py` exposing `class AuditScrubService` with:
  - `async def scrub(*, org_id: UUID, dpo: CurrentActor, filter: ScrubFilter, dry_run: bool) -> ScrubResult`
  - Filter validation: at least one populated field; unknown keys raise `ScrubFilterError`.
  - Wet path: opens `migrator_session_scope`, runs `UPDATE audit_log SET intent_metadata = jsonb_set(...) WHERE organisation_id = :org AND <filter> AND NOT (intent_metadata ?& array['<scrubbed-marker>'])`, captures `rows_scrubbed`, calls `audit.record(db, action="scrub", entity_type="audit_scrub", entity_id=<uuid4>, organisation_id=org_id, diff={...})` in the same transaction.
  - Dry path: same `WHERE`, `SELECT count(*)`, returns count, no UPDATE, no meta row.
- [ ] 2.2 Implement `ScrubFilter` Pydantic model with `actor_id?`, `ip?`, `since?`, `until?` and the unknown-key rejection (`model_config = ConfigDict(extra="forbid")`).
- [ ] 2.3 Implement `ScrubResult` Pydantic model: `{rows_scrubbed: int, dry_run: bool}`.
- [ ] 2.4 Add route `POST /api/orgs/{slug}/audit/scrub` in `backend/src/fastsaas/audit/routes.py` (new file or existing, whichever the audit module lands on first):
  - Resolves `TenantContextDep` for the slug → confirms org, sets `app.current_org`.
  - `await can(actor, Operation.SCRUB, ResourceType.AUDIT_LOG, ctx.organisation.id, db, redis)` — 403 with `code = "authz.forbidden"` on miss.
  - Delegates to `AuditScrubService.scrub`.
  - Maps `ScrubFilterError` → HTTP 400 with the `audit.scrub.empty_filter` / `audit.scrub.unknown_filter_key` codes.
- [ ] 2.5 Wire the new router into `main.py` if a top-level `audit_router` doesn't already exist.

## 3. Sentinel + redaction integration

- [ ] 3.1 Define `SCRUBBED_GDPR_LITERAL = "<scrubbed:gdpr>"` in `audit/scrub.py`. Re-export from `audit/__init__.py` as part of the public extension surface.
- [ ] 3.2 Confirm the scrub UPDATE replaces ONLY `intent_metadata.{ip, user_agent, original_prompt, path}` and leaves any future fields untouched — write the `jsonb_set` chain explicitly per field rather than `intent_metadata = '{}'::jsonb`.
- [ ] 3.3 Add a runtime assertion at scrub-call time that compares the four target keys to a hard-coded set imported from `audit/scrub.py` — if `intent.py` ever adds a new client-controlled key without a corresponding scrub update, the assert fires in dev/test.

## 4. Wiegers documentation

- [ ] 4.1 Append "Second amendment — PII scrub contract (2026-05-05)" to `requirements/decisions/ADR-010_audit-log-shape.md`:
  - The `<scrubbed:gdpr>` sentinel and its discriminator from `<redacted>`.
  - Org-scoped, four-field-only mutation rule.
  - Meta-audit row contract (`entity_type="audit_scrub"`, etc.).
  - DPO bundle as the only path; compliance officer remains read-only.
  - Bounded exception: `actor_id` is NOT scrubbed (structural).
- [ ] 4.2 Update `requirements/formal/stakeholders/SH-compliance-officer.md`: add a "Data Protection Officer" sibling profile or a section noting the role split (read vs scrub). One file per profile is the convention — likely a new `SH-data-protection-officer.md`.
- [ ] 4.3 Update `traces_to:` frontmatter on ADR-010 to reference this change + the (new) DPO stakeholder profile.

## 5. Documentation for Claude

- [ ] 5.1 Update `backend/src/fastsaas/audit/CLAUDE.md` §"What NOT to do" — replace the "(backlog)" reference with a direct pointer to `audit/scrub.py` and the DPO bundle.
- [ ] 5.2 Add a §"Scrubbing PII for GDPR" section to `backend/src/fastsaas/audit/CLAUDE.md`: when to use it, the four-field scope, the sentinel, the meta-audit row, the dry-run flag.

## 6. Tests

- [ ] 6.1 Unit — `audit/scrub.py::ScrubFilter` validation: empty filter → `ScrubFilterError`, unknown key → `ScrubFilterError`, valid combos pass. (`tests/test_audit_scrub_filter.py`)
- [ ] 6.2 Unit — `AuditScrubService.scrub` dry-run: returns matched count, no UPDATE issued (assert via mocked execute or row-snapshot). (`tests/test_audit_scrub_service.py`)
- [ ] 6.3 Integration — DPO scrubs by `actor_id`, only `intent_metadata.{ip, user_agent, original_prompt, path}` are replaced, structural columns unchanged byte-for-byte. (`tests/test_audit_scrub_integration.py`)
- [ ] 6.4 Integration — Compliance officer (read-only) hits scrub endpoint → 403, no rows modified.
- [ ] 6.5 Integration — Non-DPO member hits scrub endpoint → 403.
- [ ] 6.6 Integration — Meta-audit row appended exactly once per wet scrub; not appended for dry-run.
- [ ] 6.7 Integration — Re-running same scrub returns `rows_scrubbed: 0`; meta row still appended.
- [ ] 6.8 Integration — Cross-org isolation: DPO of `acme` cannot scrub `globex` rows even with matching `actor_id` filter.
- [ ] 6.9 Integration — `dry_run: true` does NOT write a meta-audit row.
- [ ] 6.10 Integration — Scrubbed rows still appear in compliance officer cross-org reads (the structural row is preserved; only PII fields differ).

## 7. Validation + close-out

- [ ] 7.1 `openspec validate audit-pii-scrub --strict` passes.
- [ ] 7.2 `cd backend && uv run ruff check .` clean.
- [ ] 7.3 `./run_test.sh -q` green.
- [ ] 7.4 PR opened, linked to issue #13.
- [ ] 7.5 Archive change after merge; sync delta specs to `openspec/specs/audit/`.
