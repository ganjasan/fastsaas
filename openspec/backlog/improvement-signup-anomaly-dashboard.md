# Signup Anomaly Dashboard via audit_log

**Type**: improvement
**Priority**: medium
**Area**: backend+frontend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Admin-only dashboard that surfaces registration / magic-link / password-reset anomalies in the last 24h / 7d. Built on top of the existing `audit_log` table (per ADR-006/010) — Phase 1+2 defenses each write `audit.record(action='abuse.*', ...)` rows, so this dashboard is a query, not a new schema.

Mapsurvey's 2026-05-07/08 incident was caught by happenstance — looking at user-outreach reports and noticing 41 unfamiliar usernames. With this dashboard, the same pattern would have been visible in minutes. The Mapsurvey post-deploy verification on 2026-05-09 already showed real-world value: a real bot caught 4 minutes after defenses went live, recorded in the audit log, immediately visible.

## Goals

- Detect registration spikes within minutes of them starting, not days.
- Give a one-glance ops view: "Is anything weird happening on signups right now?"
- Cheap to build because the data is already in `audit_log`.

## What to Show

### Cards (top)

- **Triggered defenses, last 24h** — count by `action` (`abuse.captcha_failed`, `abuse.rate_limited`, `abuse.honeypot_triggered`, `abuse.email_domain_blocked`).
- **Successful registrations, last 24h** — count of `auth.register.completed` audit rows.
- **Verification-conversion rate** — registrations that completed verification / total registrations triggered. Phase 2 makes this much cleaner.

### Charts

- **Triggered defenses per hour, last 7 days** — sparkline per defense type, baseline-aware (highlight days >3σ over rolling baseline).
- **Top source IPs, last 24h** — table of IPs with >2 triggered-defense events. Drill-down link.
- **Top email domains, last 24h** — flag unexpected ones (especially recently-seen disposable ones not yet on the blocklist).

### Pattern alerts

- **Username pattern anomaly counter** — count of signup attempts with usernames matching `^[a-z]{10}$` (the Mapsurvey 2026-05-08 bot pattern). This single regex would have flashed red on day 1 of that attack.
- **Email-prefix collision rate** — count of distinct accounts sharing the local-part-before-the-@. Email-bombing signature.

## Implementation Notes

- Backend: new endpoint `GET /admin/abuse/dashboard` returning aggregated JSON. Reuses existing `audit_log` queries — no schema changes.
- Authorization: admin-only via the existing `capability` system (per ADR-013). New capability `admin.abuse.read` bundled into the `staff` role.
- Frontend: new admin page in `frontend/src/features/admin/` rendering the JSON. Reuses existing admin-page chrome / styling.
- Refresh: button-only, no real-time push. Polling is overkill for this traffic.
- Optional: weekly digest email to admins ("X registrations this week, Y triggered defenses, anomalies: …").
- Search-palette integration: register `SearchProvider` for `audit_event` so admins can `⌘K → "honeypot triggered"` and jump to recent events. Per CLAUDE.md "every user-facing entity registers a SearchProvider" — applies if we expose this dashboard as findable.

## Out of Scope

- ML-based detection — too much for the scale.
- Automatic blocking based on dashboard signals — keep human-in-the-loop. Dashboard surfaces, ops decides.
- Public / customer-facing stats — this is internal admin tooling.
- IP geolocation lookup — adds dep, not worth for v1.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-verify-before-account.md (cleaner conversion metrics once that lands)
- Reuses: the existing `audit_log` table (ADR-006, ADR-010), capability-based authz (ADR-013), search-palette infrastructure.

## Why this is "improvement" not "feature"

The data and the actions are both already in place — this is a UI that surfaces what the audit log already captures. No new behavior, just observability.
