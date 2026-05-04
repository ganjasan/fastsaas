---
id: SH-compliance-officer
title: Compliance Officer
kind: stakeholder-profile
status: draft
created: 2026-05-04
author: Artem Konuchov (с Claude Code)
traces_to:
  related_adr:
    - ADR-007  # Multi-tenant isolation (compliance amendment for audit access)
    - ADR-010  # Audit log shape (immortal table, tenant-scoped reads)
    - ADR-013  # Authorization — capabilities + role bundles (role:compliance_officer)
  related_use_cases:
    - "UC-002 [A5]"   # HQ compliance audit cross-org (cross-dept variant rejected per Decision #12; cross-org concept survives)
    - UC-008          # API key rotation auditing (depends on audit reads)
    - UC-010          # Org policy denial auditing (depends on audit reads)
  related_change: openspec/changes/audit-trail-middleware
  related_features: []
---

# SH: Compliance Officer

> Profile written in Wiegers style (Software Requirements, 3rd ed., Ch. 6 — *Stakeholder Analysis*). Pinned at `draft` until reviewed by an actual compliance practitioner.

## Description

Person (typically a single named individual per customer-org, sometimes a small team in larger enterprises) accountable for verifying that the operational behaviour of FastSaaS-hosted services meets the org's regulatory obligations — SOC 2, ISO 27001, industry-specific frameworks (HIPAA / GDPR / financial), and internal audit policies.

In SMB orgs the role is held part-time by an Org Admin or external auditor on a quarterly cadence. In enterprise orgs it is a dedicated full-time function, possibly with a CISO chain of command. FastSaaS as a starter kit must serve **both** patterns from one capability primitive — `role:compliance_officer` per ADR-013.

## Representative

No real-world representative engaged yet. **Open question** flagged in §"Pain points" — a real Compliance Officer interview is required before this profile is promoted out of `draft`.

## Тип участия

- [x] Пользователь системы — read-only, on the audit-log surface
- [ ] Заказчик / покупатель — typically not the buyer (Customer is Org Admin / CISO), though influences the buy decision through compliance gating
- [ ] Спонсор
- [ ] Технический поставщик
- [x] Регулятор — second-order, via the external frameworks they enforce

## Goals (what the system must deliver)

1. **Provable audit trail** — every mutation in the org's domain is captured in `audit_log` with `actor_id`, `intent_hash`, `entity_type / entity_id`, before/after `diff`, and `intent_metadata` (request_id, IP, UA, optional `original_prompt` for AGENT-initiated actions). Coverage gaps are unacceptable; missing rows mean failed compliance.
2. **Investigation in minutes, not hours** — for any incident the officer can reconstruct: «what did actor X do between dates A and B», «who touched entity Y», «what changed when policy P was created / overridden». Without joins to per-domain tables.
3. **Regulator response artifact** — exportable report (SQL CSV today, structured PDF later via `#5` admin surface) that an external auditor accepts as primary evidence.
4. **Trustworthy long-term retention** — audit rows must not be tampered with after the fact. ADR-010's immortality + RLS write-only policies are the trust anchor.
5. **Survival across schema changes** — when downstream domains (`scenarios`, `analyses`, …) are added, audit must keep working without an officer-side reconfiguration. The open-vocabulary `entity_type` contract is exactly that.

## Responsibilities and authority

**Authority (what they CAN do):**
- Read `audit_log` cross-org via the `app.role = 'compliance_officer'` GUC + `role:compliance_officer` capability gate.
- Issue compliance reports / regulator responses based on those reads.
- File findings and require remediation through the Org Owner (out of band — not a system action).

**Out of authority (what they explicitly CANNOT do):**
- Mutate any operational data — projects, scenarios, members, capabilities.
- Change `org_policies` or override `policy_blocked` capabilities (ADR-016 reserves overrides for the Org Owner alone).
- Issue or revoke other actors' capabilities, including their own.
- Read operational tables outside `audit_log` (`projects.*`, `scenarios.*`, …).
- Erase or modify audit rows (immortality is a hard invariant).

The strict read-only scope is itself the compliance signal — an officer who could mutate would not be a credible auditor.

## Tasks the system must support

1. **Run a structured audit query** — by actor, by entity, by time window, by `entity_type`, by `intent_hash` prefix (`agent:` to isolate AGENT-initiated activity).
2. **Export the matched rows** — CSV today, formatted PDF via the future admin surface.
3. **Reconstruct an incident timeline** — joining `audit_log` rows by shared `intent_hash` (a multi-step UI flow shares a single `sess:` hash) or by an entity's `entity_id`.
4. **Verify policy compliance** — confirm that no AGENT actor performed a forbidden action (e.g. `delete:organisation`); confirm that `org_policy_overrides` were appropriately scoped.
5. **Quarterly attestation** — assemble the standard "what changed this quarter" report for SOC-2 evidence package.

## Requirements derived from this profile

(Linked to spec deltas in `audit-trail-middleware`, will be amended as the change lands.)

- Every domain mutation produces an audit row in the same transaction (spec `audit/spec.md` §"Every domain mutation produces an audit row").
- Sensitive fields never appear in audit diffs (spec §"Sensitive fields never appear in audit diffs").
- `entity_type` is open-vocabulary so downstream stays auditable (spec §"`entity_type` is an open string vocabulary").
- `actor` and `intent` flow through contextvars so no mutation can write an audit row without identifying the initiator (spec §"`actor` and `intent` flow through contextvars").
- Cross-org reads gated on `role:compliance_officer` + `app.role` GUC (spec §"Audit log reads are tenant-scoped except for compliance-officer").

## Success metrics

- **Coverage**: 100% of service-layer mutations produce audit rows (verified by integration tests; downstream gets the same property by inheriting from `AuditedModel` or calling `record(...)` per the audit module's CLAUDE.md).
- **Time-to-trace**: arbitrary "who/what/when" query answerable in < 5 minutes by an officer with SQL knowledge, without involving engineering.
- **Readability**: a row's `diff` and `intent_metadata` are human-readable without decoding — no opaque blobs, sensitive fields cleanly redacted as `"<redacted>"` (presence-of-key still visible).
- **Audit immutability**: zero successful UPDATE/DELETE attempts against `audit_log` recorded over the audit window (RLS write-only policy enforces this; should be verified by penetration test before SOC-2 attestation).

## Pain points / risks

1. **Real-world representative not yet engaged.** Profile based on textbook compliance role + analogues (AWS CloudTrail, GitHub audit log, Vault audit devices). A live interview will sharpen requirements, especially around report formatting and quarterly cadence specifics. Action: schedule before #4 archives.
2. **Capability creep.** Pressure will come to extend `role:compliance_officer` with read access to operational tables ("just to verify"). Resist — it dilutes the read-only-auditor signal. New investigative needs go through a separate, auditable Org-Owner-issued time-bounded capability per ADR-016 override flow.
3. **GDPR vs immortality.** EU/UK customers will want audit-log scrubbing for right-to-erasure requests. ADR-010 § Open Questions notes a future endpoint that scrubs PII inside `intent_metadata` (IP, UA, `original_prompt`) while preserving the structural trail. Policy-side question for the officer: which fields are PII, what's the retention window, how is scrubbing itself audited.
4. **Coverage drift on downstream entities.** If a downstream developer ships a new domain table without inheriting from `AuditedModel` and without explicit `record(...)` calls, the audit gap is silent — there's no compile-time signal of "you forgot audit". Mitigations:
   - The audit module's CLAUDE.md is the explicit guide for Claude-driven downstream work.
   - The ADR-010 amendment formalises the contract.
   - Open question: should we ship a CI check that warns when a new SQLModel `table=True` class doesn't inherit `AuditedModel` and isn't on an explicit allowlist? Tracked as backlog.
5. **Cross-org concept after Decision #12 rejection.** The original "HQ compliance audit cross-departmental" use case (UC-002 [A5]) was scoped against a Department entity that no longer exists in v1. The cross-org concept (compliance officer of a multi-org consultancy reading across all their orgs) survives — but UC-002 itself needs reconsideration. Tracked in `tasks.md` of the spike change as a backlog item.

## Constraints and preferences

- **Technical fluency**: SQL-literate. Comfortable with `WHERE` / `JOIN` / time-window queries, JSON path operators (`metadata->>'org_id'`). Not a developer — won't read Python source to figure out what an `entity_type` means; the CLAUDE.md and ADR-010 are the canonical references they should be able to read.
- **Tooling preference**: a SQL client + CSV export today; a thin admin UI later (via `#5` design system surface). No need for a bespoke compliance dashboard in v1.
- **Language**: English for the audit log content; Russian/local language acceptable for narrative reports (officer's choice).
- **Availability for interviews**: Medium — typically billable, time-boxed quarterly. Schedule with stakes named.
- **Frequency of system interaction**: episodic. Quarterly attestations + incident response (ad-hoc, ~1–4 times/year for a healthy SaaS). Not a daily user.

## Влияние на проект: **Среднее**

Doesn't drive new features but absolutely gates SOC-2 / industry-compliance certification — without that gate the platform can't sell into regulated B2B. Their veto on coverage / immutability is firm.

## Интерес к проекту: **Средний**

Cares about the audit primitive, the role definition, and the report format. Indifferent to most of the rest of the platform (UI polish, design system, devex).

## Stakeholder matrix placement: **Управляй** (high-influence × medium-interest)

Keep informed at architecture-decision level (ADR amendments visible to them); don't burden with daily implementation detail. When a decision touches audit shape / role scope / retention, loop them in synchronously.

## Questions for the next interview

1. Which compliance frameworks are in actual scope for the first paying customer? (SOC-2 Type 2 alone or also industry-specific HIPAA/PCI/financial?)
2. What format does your external auditor expect for the evidence package? (PDF report, CSV dump, signed-tarball, …)
3. How long must we retain audit rows? (7 years for many frameworks; varies.)
4. What's your pain point with current audit tooling at your existing platforms? Which queries took too long to write?
5. Would you want a self-service audit UI in v1, or is SQL+CSV acceptable for the first 12 months?
6. How do you envision GDPR right-to-erasure interacting with audit retention? Field-level scrubbing acceptable or do you need full-row deletion?
7. What's the expected separation of duties between Compliance Officer, Org Admin, and Org Owner in your operating model?

## References

- [[../../decisions/ADR-007_multi-tenant-isolation]] — RLS + the compliance-officer audit-access amendment.
- [[../../decisions/ADR-010_audit-log-shape]] — table shape + immortality + open `entity_type` vocabulary (see § Extension contract once the ADR-amendment from change `audit-trail-middleware` lands).
- [[../../decisions/ADR-013_authorization-capabilities-role-bundles]] — `role:compliance_officer` bundle definition.
- [[../use-cases/UC-002_organization-departments-isolated-modeling]] — UC-002 [A5] cross-dept audit alternate flow (rejected at Decision #12 for the dept entity; cross-org compliance read survives).
- [[../use-cases/UC-008_api-key-rotation-and-revocation]] — depends on audit reads.
- [[../use-cases/UC-010_org-policy-on-agent-scopes]] — depends on audit reads.
- `openspec/changes/audit-trail-middleware/` — active change wiring this profile's requirements into core.
