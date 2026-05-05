---
id: SH-data-protection-officer
title: Data Protection Officer (DPO)
kind: stakeholder-profile
status: draft
created: 2026-05-05
author: Artem Konuchov (с Claude Code)
traces_to:
  related_adr:
    - ADR-007  # Multi-tenant isolation (org as GDPR controller boundary)
    - ADR-010  # Audit log shape (immortality + 2026-05-05 PII scrub amendment)
    - ADR-013  # Authorization — capabilities + role bundles (role:dpo)
  related_use_cases: []
  related_change: openspec/changes/audit-pii-scrub
  related_features: []
  sibling_profiles:
    - SH-compliance-officer  # reads audit log; DPO erases PII per Art.17 — separate roles by design
---

# SH: Data Protection Officer (DPO)

> Profile written in Wiegers style (Software Requirements, 3rd ed., Ch. 6 — *Stakeholder Analysis*). Pinned at `draft` until reviewed by an actual DPO practitioner.

## Description

Person (typically a single named individual per customer-org under GDPR Art. 37, sometimes shared across affiliated orgs) accountable for handling data-subject requests under the EU and UK General Data Protection Regulations — specifically right-to-erasure (Art. 17), right-of-access (Art. 15), and right-to-rectification (Art. 16). Within FastSaaS the role is reified by the `role:dpo` bundle (ADR-013) which carries `read + scrub` on `audit_log` for the org.

The role is intentionally separate from the Compliance Officer (SH-compliance-officer): compliance reads, DPO erases. A single individual MAY hold both bundles, but the capability split makes that an explicit grant rather than an implicit consequence of being "the audit person".

In SMB orgs without a regulatory presence the bundle is often unassigned; the org has no DPO function until they onboard their first EU/UK data subject. In enterprise orgs with an established privacy office, DPO is a dedicated role with audit-trail of every erasure they perform.

## Representative

No real-world representative engaged yet. **Open question** flagged in §"Pain points" — a real DPO interview is required before this profile is promoted out of `draft`.

## Тип участия

- [x] Пользователь системы — read + scrub on `audit_log`
- [ ] Заказчик / покупатель — typically not the buyer (Org Admin / CISO buys); influences buy decision through compliance gating in EU/UK markets
- [ ] Спонсор
- [ ] Технический поставщик
- [x] Регулятор — second-order, via the data-protection authority they answer to (e.g. Ireland's DPC, UK ICO, German BfDI)

## Goals (what the system must deliver)

1. **Provable erasure path** — when a data subject requests right-to-erasure under Art.17, the DPO can locate every row carrying that subject's PII and zero those fields, without breaking the structural audit trail. A failed erasure is a regulatory violation; the platform must not refuse or partially fulfil.
2. **Auditable scrub itself** — every scrub call writes one `audit_scrub` meta-row capturing the filter and row count. Regulators ask "prove the erasure was performed and was scoped correctly"; the meta row is the answer.
3. **Dry-run before commit** — for unfamiliar filters (e.g. by IP across a date range) the DPO previews the matched count before mutating. Mistakes on a destructive endpoint are expensive to explain.
4. **Org-scoped by construction** — each org is a separate GDPR controller. A DPO of org A must not be able to scrub org B's rows even by accident. The endpoint enforces this at the URL level (slug-resolved org id, not a user-supplied filter).
5. **No ambiguity about what is and isn't erased** — `<scrubbed:gdpr>` literal is distinct from `<redacted>`. A row's reader can tell at a glance: "this field was always sensitive (redacted at write)" vs "this field carried PII that was erased post-hoc on a subject request". The structural columns (`actor_id`, `entity_type`, `entity_id`, `action`, `intent_hash`, `diff`) survive the scrub.

## Responsibilities and authority

**Authority (what they CAN do):**

- Read `audit_log` for their org — same as Compliance Officer.
- Scrub `audit_log.intent_metadata.{ip, user_agent, original_prompt, path}` for filtered rows in their org via `POST /api/orgs/{slug}/audit/scrub`.
- Run dry-run scrubs to preview affected rows.
- Document every erasure decision out-of-band as part of the GDPR records-of-processing.

**Out of authority (what they explicitly CANNOT do):**

- Mutate any operational data outside `audit_log` (projects, members, capabilities — those are Org Owner / Admin scope).
- Erase structural audit columns (`actor_id`, `entity_type`, `entity_id`, `action`, `diff`, …). The scrub endpoint does not touch them, by construction. A subject who asks for `actor_id` removal is told "no" — the structural trail is the legitimate-interest carve-out under Art.17(3).
- Cross-org scrub. If the same person is in orgs A and B, each org's DPO acts within their own org; there is no platform-level "scrub everywhere" path.
- Override the role split — DPO does NOT acquire `role:compliance_officer` rights or vice versa via this bundle. Holding both is an explicit owner-issued grant.

The strict scope is itself the GDPR signal: a DPO who could mutate operational data would not be a credible privacy officer.

## Tasks the system must support

1. **Locate a subject's audit footprint** — query `audit_log` for `WHERE actor_id = X` or `WHERE intent_metadata->>'ip' = 'a.b.c.d'` to enumerate the rows that would be scrubbed.
2. **Preview the scrub** — `POST /api/orgs/{slug}/audit/scrub` with `dry_run: true` to confirm the filter matches the expected rows.
3. **Execute the scrub** — same endpoint with `dry_run: false`. Receive `rows_scrubbed: N` and trust the meta-audit row was written.
4. **Verify the scrub** — re-query the rows to confirm `intent_metadata.{ip, user_agent, original_prompt, path}` now equal `"<scrubbed:gdpr>"` and the structural columns are unchanged.
5. **Show evidence to a regulator** — produce the `audit_scrub` meta row(s) with the original filter and row count as the records-of-processing entry.

## Requirements derived from this profile

(Linked to spec deltas in `audit-pii-scrub`.)

- Audit log PII fields are scrubbable via a sanctioned endpoint (spec `audit/spec.md` §"Audit log PII fields are scrubbable via a sanctioned endpoint").
- Dry-run mode mutates nothing (spec §"Scrub endpoint supports dry-run mode that mutates nothing").
- Wet scrub writes one meta-audit row (spec §"Every wet (non-dry-run) scrub call writes one meta-audit row").
- Filter rejects empty bodies and unknown keys (spec §"Scrub filter rejects empty bodies and unknown keys").
- New `Operation.SCRUB` and `role:dpo` bundle (spec §"New `Operation.SCRUB` capability and `role:dpo` bundle").
- Scrub is org-scoped (spec §"Scrub is org-scoped and refuses cross-org filters").

## Success metrics

- **Coverage**: every PII-bearing key in `intent_metadata` (per `PII_INTENT_KEYS`) is scrubbed by the endpoint. The module-level assert in `audit/scrub.py` fails CI if a new key drifts in without the scrub set being extended.
- **Time-to-erase**: a typical erasure request (filter by `actor_id`) completes in < 5 minutes from receipt to confirmation, without engineering involvement.
- **Auditability**: 100% of wet scrub calls produce one `audit_scrub` meta row in the same transaction (verified by integration test). Zero "we scrubbed but can't prove it" cases.
- **Org-scope correctness**: cross-org scrub attempts (slug A, filter targeting B's data) cannot mutate B's rows. Verified by integration test.

## Pain points / risks

1. **Real-world representative not yet engaged.** Profile based on textbook GDPR DPO role + Art.37/38/39 obligations + analogues (AWS GDPR data-subject-access toolkit, Stripe's privacy-request tooling). A live interview will sharpen requirements, especially around evidence formatting and the records-of-processing artefact.
2. **`actor_id` non-scrubbability disagreement.** A subject who asks for full erasure may push to have `actor_id` removed too. The platform's position is that `actor_id` is the structural join key; removing it destroys the audit trail's purpose. This is a defensible position under Art.17(3)(b) ("legitimate interest" carve-out for compliance), but a DPO may need to escalate or get legal sign-off in contested cases. Document the position clearly in customer-facing privacy policy.
3. **Coverage drift on `intent_metadata`.** If a future PR adds a new client-controlled key to `intent.py` (e.g. `geo`) and forgets to extend `SCRUBBED_FIELDS`, the new key is not scrubbed. The module-level assert is the mechanical guard; the ADR-010 amendment is the human one. Both must hold.
4. **Retention-driven scrub vs subject-driven scrub.** This change is for subject-driven erasure only. A retention-policy-driven scrub (zero PII on rows older than N days) is a separate ticket with its own sentinel `<scrubbed:retention>`. Conflating the two would muddy the analytical distinction in the audit data.
5. **DPO bundle issuance.** The first DPO in an org is minted by `role:owner` calling `mint_bundle` — there is no self-service flow yet. For an enterprise that hires their DPO before bringing them onto the platform, the owner has to do this manually. UI and onboarding flow are separate tickets.
6. **Single-controller model.** GDPR allows joint controllers (Art.26). Today FastSaaS treats each org as a sole controller; a configuration where org A and org B are joint controllers of the same dataset is not modelled. Acceptable for v1; flag if a customer asks.

## Constraints and preferences

- **Legal fluency**: high — knows GDPR articles, knows the difference between erasure, rectification, and access. NOT a developer; reads the ADR amendment, not the Python source.
- **Technical fluency**: medium — SQL-literate, comfortable with HTTP / JSON / curl. Will use the API directly today; a thin admin UI later.
- **Tooling preference**: an authenticated HTTP client (curl, Insomnia) + a SQL client for verification. The API contract documented in OpenAPI is enough for v1.
- **Language**: English for the audit log content; local language acceptable for the records-of-processing report (DPO's choice).
- **Availability for interviews**: Low — DPOs are stretched and often hold the role part-time alongside other counsel work. Schedule with stakes named.
- **Frequency of system interaction**: rare and bursty. Erasure requests come in waves (e.g. after a viral product moment, after a security disclosure); steady state is a handful per year per org for an SMB.

## Влияние на проект: **Среднее**

Gates the EU/UK go-live: without a working erasure path the platform can't legally accept European data subjects. Once shipped, the role's day-to-day footprint is small.

## Интерес к проекту: **Средний**

Cares about the scrub primitive, the role split, the evidence artefacts. Indifferent to most other platform features.

## Stakeholder matrix placement: **Управляй** (high-influence × low-interest)

Keep informed at architecture-decision level (ADR amendments visible to them); don't burden with daily implementation detail. When a decision touches audit shape, retention, or PII scope, loop them in synchronously.

## Questions for the next interview

1. Which jurisdictions are in scope for the first EU/UK paying customer? (GDPR alone, or also UK-GDPR, Swiss FADP, others?)
2. What evidence format do your supervisory authorities (DPC, ICO, …) expect for an erasure response?
3. What is the maximum legal turn-around time you operate under? (Art. 12(3): one month standard, extensible to three for complexity.)
4. Are there cases where a subject's `actor_id` itself must be removed? How would you escalate when our platform refuses?
5. How do you currently document the records-of-processing for erasure requests on other platforms? Is the `audit_scrub` meta row enough?
6. Would you want a self-service UI in v1, or is the HTTP endpoint + SQL verification acceptable for the first 12 months?
7. Joint-controller cases: do you operate any datasets where another org is a joint controller? How critical is modelling that in v1?
8. Retention-driven scrub: do your retention policies require automated zeroing of PII on aged rows? At what cadence?

## References

- [[../../decisions/ADR-007_multi-tenant-isolation]] — org as GDPR controller boundary.
- [[../../decisions/ADR-010_audit-log-shape]] — see § "2026-05-05 PII scrub contract" amendment.
- [[../../decisions/ADR-013_authorization-capabilities-role-bundles]] — `role:dpo` bundle definition.
- [[SH-compliance-officer]] — sibling stakeholder; reads but does not erase.
- `openspec/changes/audit-pii-scrub/` — active change wiring this profile's requirements into core.
