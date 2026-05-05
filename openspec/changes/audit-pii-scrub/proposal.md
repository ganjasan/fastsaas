---
title: Audit PII scrub endpoint — GDPR Art. 17 right-to-erasure for `audit_log.intent_metadata`
status: in_progress
linked_issue: ganjasan/fastsaas#13
created: 2026-05-05
traces_to:
  adr:
    - "[[ADR-006_primary-keys-and-cascade]]"
    - "[[ADR-010_audit-log-shape]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  use_cases:
    - "UC-002 [A5] (compliance officer cross-dept audit)"
  stakeholders:
    - "[[SH-compliance-officer]]"
---

## Why

`audit_log` is immortal per ADR-006/010 — RLS exposes no UPDATE/DELETE policies for the `app_user` role. Correct for the structural trail, **incompatible with GDPR Art. 17 / UK-GDPR right-to-erasure** for PII that lands inside `intent_metadata`:

- `intent_metadata.ip` — personal data under GDPR
- `intent_metadata.user_agent` — fingerprintable
- `intent_metadata.original_prompt` — may contain user-typed PII
- `intent_metadata.path` — may carry identifiers in URL segments

Without a sanctioned scrubbing path, the only options when a data subject requests erasure are: refuse, drop the row entirely (loses the structural trail), or drop the table (catastrophic). All three are wrong.

Identified during PR #12 security review (audit-trail-middleware) and explicitly nodded to in ADR-010 ("future endpoint that anonymises PII inside `intent_metadata` while keeping `actor_id`, `entity_type`, …"). This change ships that endpoint.

**Why P1 / blocker for EU/UK launch.** The moment we onboard the first EU data subject, immortal `audit_log` becomes a legal liability without this path.

## What changes

1. **New `Operation.SCRUB` capability** on `ResourceType.AUDIT_LOG`. Strictly stricter than `READ` — read does not imply scrub.
2. **New bundle `role:dpo`** (Data Protection Officer): grants `read + scrub` on `audit_log`. Compliance officer keeps read-only. DPO is the role that handles erasure requests.
3. **Org-scoped endpoint** `POST /api/orgs/{slug}/audit/scrub` accepting filter (actor_id, ip, date range — AND-combined) and a `dry_run` flag. Returns count of rows that would be / were scrubbed.
4. **`AuditScrubService.scrub`** runs in `migrator_session_scope` (BYPASSRLS), targets `audit_log` rows by filter, and replaces `intent_metadata.{ip, user_agent, original_prompt, path}` with the literal `"<scrubbed:gdpr>"`. Structural columns (`entity_type`, `entity_id`, `action`, `actor_id`, `organisation_id`, `timestamp`, `intent_hash`, `diff`) untouched.
5. **Meta-audit row** per scrub call: `entity_type="audit_scrub"`, `action="scrub"`, `diff={"filter": {...}, "rows_scrubbed": N}`. The scrub itself is logged.
6. **ADR-010 second amendment** formalising the `<scrubbed:gdpr>` sentinel and the scrub contract (org-scoped, never touches structural columns, idempotent, always meta-audited).
7. **Compliance officer stakeholder profile** updated with the DPO workflow.

## What does NOT change

- The `audit_log` migration (no new columns, no DDL).
- RLS policies on `audit_log` — the scrub bypasses RLS via the migrator role; the capability check is what gates the path.
- Existing redaction (`<redacted>`) — that's the at-write-time mask for sensitive columns; this change adds the post-hoc `<scrubbed:gdpr>` for client-controlled PII.
- The compliance officer role — it stays read-only.

## Out of scope

- Cross-org platform admin scrub (`/api/admin/...`). Added later if a tenant-of-tenants need emerges; GDPR controllers are the orgs themselves, so org-scoped covers it.
- An admin UI for the scrub flow — separate ticket.
- Automated retention-driven scrub (cron job that scrubs rows older than N days). Different problem; this change is about subject-driven erasure.
- A `<scrubbed:retention>` second sentinel for retention-driven scrub — defer until that ticket.
