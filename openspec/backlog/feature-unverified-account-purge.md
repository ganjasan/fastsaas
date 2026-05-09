# Auto-Purge of Unverified Accounts

**Type**: feature
**Priority**: medium
**Area**: backend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Periodic job that deletes:
- pending-signup tokens that never confirmed within N days (after [feature-verify-before-account.md](feature-verify-before-account.md) ships)
- legacy `User` rows where `email_verified=False` and never logged in (transitional, while the legacy unverified cohort exists)

This is housekeeping. Even after Phase 1+2 defenses ship, some bots get through, and some real users sign up but never click the verification link. Both should be removed automatically.

## Goals

- Keep `users` / `actors` clean of inactive cruft.
- Remove bot/abandoned accounts without manual ops (Mapsurvey's 41-account cleanup took 30 minutes of SQL — should be a cron, not a fire drill).
- Improve quality of "active users" metrics for downstream product analytics.
- Stop unbounded growth of the `pending_signup` table.

## Proposed Rules

| Rule | Action | Window |
|---|---|---|
| Pending signup never confirmed | Delete token row | 7 days |
| Legacy unverified user row, never logged in | Delete (cascade through Org / Memberships if any — none expected for unverified) | 30 days |
| Verified user, never logged in after registration, no Org membership beyond personal | Notify ("come back?"), then delete | 90 + 14 days |
| Verified user, abandoned Org with no other members | Notify Org owner. If still abandoned after notification window — purge Org. | Separate concern, deferred |

The third rule is conservative — it gives users an opportunity to come back before the row goes away. Discuss with product before enabling per downstream SaaS.

## Scope

### In Scope

- FastAPI background job in `backend/src/fastsaas/abuse/purge.py`. Either:
  1. APScheduler running in-process (simpler, but ties to single-instance deploys).
  2. Standalone CLI script `fastsaas-purge` invoked by a cron in `infra/` (Render Cron Job, k8s CronJob, etc.). Recommend this — works at any scale.
- Idempotent dry-run mode (`--dry-run`) for verification.
- Audit-log row per purge batch summarizing what was deleted, with row counts (NOT individual user emails — GDPR / minimal-PII per ADR-006).
- Foreign-key chain handling: pending_signup is leaf (no FKs into it); for legacy unverified users, cascade-delete via the existing Membership / Project relationships. Document the order in case manual SQL is ever needed (Mapsurvey's 2026-05-08 cleanup hit a `survey_membership` FK that wasn't anticipated; we want to avoid that surprise here).

### Out of Scope

- Soft-delete with retention period — go with hard-delete + audit log of counts.
- Differential / "unsubscribe me" UI flows — orthogonal.
- Privacy-of-deletion (GDPR right-to-be-forgotten) — separate concern, different epic.

## Open Questions

- Honor a "preserve my account please" flag if the user opts in? Probably overkill for v1 — re-registration is cheap.
- Email notification before deletion (rule 3) — coordinate with the marketing / product team on copy and frequency.
- Run the purge as a CLI invoked by infra cron, or as an APScheduler task in-process? CLI is more 12-factor; APScheduler is one fewer infra dep. Recommend CLI (separate process, simpler reasoning, observable via cron logs).

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-verify-before-account.md (Phase 2 prerequisite — once that lands, this becomes mostly "purge pending_signup rows older than 7 days")
- Sibling: improvement-signup-anomaly-dashboard.md (Phase 3 — purge stats are surfaced there)
