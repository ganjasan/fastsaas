## Context

`audit_log` is immortal (ADR-006/010): RLS has no UPDATE/DELETE policies for the `app_user` role; only the migrator (`BYPASSRLS`) can write at all, and even the migrator is forbidden by review convention from mutating rows after insert. The 2026-05-04 amendment to ADR-010 (PR #12) formalised the contract: "Do NOT mutate `audit_log` rows after the fact… If GDPR scrubbing is needed, use the dedicated PII-redaction endpoint (backlog) — it preserves the structural trail and only zeroes fields inside `intent_metadata`."

This change is that endpoint.

## Goals

- Provide a sanctioned mutation path that erases PII from `audit_log` without breaking the structural-trail guarantee.
- Keep the operation logged (meta-audit) so a scrub itself is provable.
- Gate the path on a capability that is strictly stricter than read access — a compliance officer who can read all audit rows must NOT thereby be able to erase them.
- Make the scrub idempotent and dry-runnable so DPOs can preview before mutating.

## Non-goals

- Cross-org platform admin scrub. Each org is its own controller under GDPR; org-scoped scrub covers the legal need.
- Retention-policy automation. A separate cron-driven path with its own sentinel and capability.
- An admin UI. Backend + capability only; UI ticket follows.

## Decisions

### D1 — Sentinel string is `<scrubbed:gdpr>`, not `<redacted>` or empty

`<redacted>` is already in use by the at-write-time denylist (`audit/redact.py`). Reusing it would lose the analytical distinction "this row's PII was always redacted" vs "this row's PII was scrubbed post-hoc due to a subject request". The `:gdpr` tag is the prefix that lets a future retention-driven scrub use `<scrubbed:retention>` without conflicting.

Empty string is wrong: presence-of-key is signal — the compliance officer can tell that the row originally had a `user_agent` even after the value is gone, same principle as `<redacted>`.

**Rationale.** Distinguishability for analytics + alignment with the existing redaction sentinel pattern (literal value, not omission).

### D2 — Scope = org, not actor or row

The scrub takes a filter (actor_id, ip, date range) and applies it within one org. **Why not "scrub by row id"?** Because erasure requests are about a person, not a row — a DPO who locates a subject by IP needs to scrub all of their rows, not click through each. **Why not "scrub by actor across all orgs"?** Because each org is a separate GDPR controller; the actor's data in org A is org A's responsibility, not the platform's. If the same person is in orgs A and B, each DPO scrubs in their own org.

**Rationale.** Maps to GDPR's controller model. Avoids accidentally privileging platform-level access.

### D3 — Filter combinator is AND, not OR

`{"actor_id": X, "ip": "1.2.3.4"}` scrubs rows where BOTH match. AND is the conservative default — narrower scope, less collateral. A DPO needing OR semantics calls the endpoint twice with separate filters.

**Rationale.** Fail-narrow on a destructive op. Composing OR from two AND calls is trivial; the inverse would require an extra "give me back the rows I wasn't supposed to scrub" path.

### D4 — Capability shape: new `Operation.SCRUB` + new `role:dpo` bundle

Adding to `Operation` enum is cheap (one StrEnum value) and keeps the `can(actor, op, resource_type, resource_id)` API uniform. Alternative — overloading `Operation.ADMIN` on `audit_log` — collapses two distinct authorisations and breaks audit-of-audit:

- A `role:owner` already has `admin organisation` but should NOT have audit scrub by default. Owners are not data protection officers.
- A `role:compliance_officer` has read but should NOT have scrub. Read and erase are different responsibilities — separating them is the standard GDPR control.

`role:dpo` bundle grants `read + scrub` on `audit_log` — minted by an org owner explicitly. Initially, in dev, the only path to mint it is `authz.service.mint_bundle`. Self-service UI for assigning DPO is a follow-up.

**Rationale.** Cleanest separation of read and erase; aligns with the "single capability primitive" principle from ADR-013.

### D5 — Migrator session, not `app_user`

The route handler resolves the actor and enforces `await can(actor, SCRUB, AUDIT_LOG, org_id)` via the `app_user` session. Once the check passes, the service swaps to `migrator_session_scope` for the actual UPDATE — `app_user` cannot mutate `audit_log` even with all capabilities (RLS has no UPDATE policy).

**Rationale.** Capability check stays on the tenant-pinned session (consistent with rest of codebase); the actual mutation must take the BYPASSRLS path because RLS forbids it on the app role.

### D6 — Meta-audit row is itself a regular `audit_log` row

A scrub call produces:
```
entity_type = "audit_scrub"
action       = "scrub"
entity_id    = uuid4()  -- synthetic, since "the scrub event" has no natural id
actor_id     = the DPO
organisation_id = the target org
diff         = {"filter": {...}, "rows_scrubbed": N}
intent_hash  = the request's intent_hash
intent_metadata = the DPO's request metadata (path/ip/user_agent — NOT scrubbed; the DPO is acting in their professional capacity, not as a data subject)
```

The meta-audit row writes via the regular `audit.record(...)` path within the same migrator transaction as the scrub UPDATE. If the UPDATE fails, the meta row rolls back too — cannot end up with "we logged a scrub but didn't perform one" or vice-versa.

**Rationale.** Scrubbability is itself audit-worthy; reusing the existing path keeps the contract uniform (scrub events appear in compliance officer reads alongside everything else).

### D7 — Dry run is a request flag, not a separate endpoint

`POST /api/orgs/{slug}/audit/scrub` accepts `{"filter": {...}, "dry_run": true}`. Dry run returns the count without mutating and **does not write a meta-audit row** — dry-runs are read-shaped, not write-shaped.

**Rationale.** One endpoint, one capability, two execution modes. Avoids the duplication of `POST /scrub/preview` + `POST /scrub`.

### D8 — Idempotency: rerunning the same scrub is a no-op (zero rows updated)

A row already containing `<scrubbed:gdpr>` in those four fields stays as-is. The UPDATE's `WHERE` clause excludes already-scrubbed rows so `rows_scrubbed = 0` for a re-run. The meta-audit row still writes — the DPO's intent to re-run is observable.

**Rationale.** Idempotency is correctness on a destructive path. The meta row choice biases towards "every action is logged" over "noise-free history".

### D9 — Filter validation is strict; unknown keys reject

Request schema: `{actor_id?: UUID, ip?: str, since?: ISO8601, until?: ISO8601}`. At least one of these must be present (no "scrub all rows in the org" path — that's a different operation, deliberately not built here). Unknown filter keys cause HTTP 400.

**Rationale.** Loose filter parsing on a destructive endpoint is a footgun. A DPO that wants "scrub everything" needs a different, narrower endpoint that doesn't exist yet — and probably shouldn't until there's a clear use case.

## Risks / trade-offs

- **Coverage gap if a new field is added to `intent_metadata`**. Today the four scrubbable fields are hard-coded. If a future PR adds `intent_metadata.geo` carrying GPS, it doesn't get scrubbed automatically. Mitigation: ADR-010 amendment lists the scrub field set; a new field on the metadata bag must extend the set or be excluded explicitly with a written reason. Backlog item: lint that flags new keys on `intent_metadata` without a scrub-set decision.
- **Meta-audit row PII**. The DPO's own `intent_metadata` (their IP, user_agent, path) lands in the meta row. Since the DPO is acting in their professional capacity, this is correct under GDPR (legitimate interest, audit trail). Documented in the ADR amendment.
- **Scrub of structural fields requested by subject**. A subject could in principle argue that `actor_id` is itself PII linking them. We don't honour that here — `actor_id` is the join key for the structural trail, removing it destroys the audit purpose. Documented as a bounded exception in ADR-010 amendment.
- **Capability creep**. The DPO bundle is new. If poorly governed it could be assigned widely and dilute the control. Mitigation: PRIMARY_BUNDLES already gives the org one role per actor; DPO is a *secondary* bundle so it's an explicit grant, not an automatic assignment.

## Migration plan

- No migration. Schema unchanged. Capability seed runs at runtime when an org bootstraps a new DPO.
- Existing orgs without a DPO simply lack the bundle until a `role:owner` mints it — same as how orgs initially had no compliance officer.

## Open questions

- **Q: Should the dry-run mode be available without `Operation.SCRUB`?** I.e., should compliance officer (read only) be able to preview what a scrub would do? Tentative: no — the capability primitive treats SCRUB as one action with two modes; opening dry-run to read-only would split the gate. Re-open if a stakeholder asks.
- **Q: What happens to meta-audit rows when a *retention* sweep wants to scrub them?** Future retention-driven scrub may want to age out very old `audit_scrub` meta rows. Not a problem for this change; flagged for the retention ticket.
- **Q: Bulk-scrub atomicity at scale.** If a single scrub matches a million rows, the UPDATE holds locks. Acceptable for the v1 — meta row records the count; if perf becomes a problem we add chunking. Not optimising prematurely.

## References

- Issue ganjasan/fastsaas#13.
- ADR-006 (primary keys + cascade — establishes immortal tables).
- ADR-010 (audit log shape) + 2026-05-04 amendment (extension contract).
- PR #12 (audit-trail-middleware) — `<redacted>` sentinel established.
- `backend/src/fastsaas/audit/CLAUDE.md` §"What NOT to do" — explicitly references this endpoint.
