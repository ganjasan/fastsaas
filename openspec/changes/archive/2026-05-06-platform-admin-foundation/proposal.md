---
title: Platform admin foundation — staff flag + /admin shell + auth gate
status: in_progress
linked_issue: ganjasan/fastsaas#19
created: 2026-05-05
traces_to:
  adr:
    - "[[ADR-009_actor-model-cti]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
    - "[[ADR-007_multi-tenant-isolation]]"
  use_cases: []
  stakeholders: []
---

## Why

The platform has org-level admins (owner / admin role bundles) but no notion of "platform staff" — operators of FastSaaS itself. Compliance reads currently fall back to direct SQL with a `app.role` GUC; DPO scrubs are curl-only; and the newly demanded admin features (orgs / metrics / health, design-system editor, auth-page config, password policy, OAuth providers) all need a cross-org actor identity that the org-scoped capability model does not express.

This change establishes the foundation. It ships:

1. A staffness flag on `actors` so an existing user can be promoted to platform staff without re-registration.
2. An extension to `can()` so platform-level resources are still gated through the single authz API (per the "capability is the only authz API" rule).
3. A skeleton admin shell at `/admin/*` with a sidebar listing the future surfaces and placeholder pages.
4. A bootstrap path so the very first staff member can be promoted via a CLI seed.
5. An ADR documenting the model so subsequent epics (#20–#23) plug in cleanly.

The shell itself is intentionally inert — every section card says "coming soon"; each follow-up issue replaces one card with a real page.

## What changes

1. **Migration 0008** — add `actors.is_platform_staff BOOLEAN NOT NULL DEFAULT FALSE`. No migration of existing rows.
2. **`Operation.PLATFORM_ADMIN` + `ResourceType.PLATFORM`** — new enum values.
3. **`can()` extension** — when `(operation, resource_type) == (PLATFORM_ADMIN, PLATFORM)`, the check returns True iff the actor's `is_platform_staff = TRUE`. No capability rows materialised; the flag IS the authority record.
4. **`Actor.is_platform_staff`** — SQLModel mirror of the new column.
5. **`/api/admin/me`** endpoint — returns the actor + flag; 403 with `code = "authz.forbidden"` for non-staff. Used by the frontend to gate the admin shell on every navigation into `/admin/*`.
6. **Frontend `<AdminShell>`** — separate layout under `routes/admin/__layout.tsx` (or equivalent), sidebar listing six items: Orgs, Metrics, Health, Design system, Auth, OAuth. Each sub-route renders a placeholder card.
7. **Bootstrap seed** — `make seed-platform-staff USER_EMAIL=<email>` flips the flag on an existing user (CLI-only; intentionally not a self-service flow).
8. **ADR-019 — Platform staff actor model** — documents the structural-vs-bundle split, why the flag (not a cross-org bundle), how to bootstrap, how subsequent epics plug in.
9. **`backend/src/fastsaas/admin/CLAUDE.md`** — module guide for downstream epics (#20–#23) explaining where their endpoints / routes / capabilities live.

## What does NOT change

- The org-level capability model. Org owners / admins still hold per-org bundles; `can(actor, op, ORGANISATION, org.id)` continues to work unchanged.
- The compliance officer + DPO roles. They remain org-scoped; platform staff is a strict superset (any platform-staff actor can still belong to orgs as a regular member).
- The audit log. No new schema; admin actions emit regular audit rows with the platform-staff actor as `actor_id`.

## Out of scope

- Real admin pages (orgs / metrics / health / etc.) — separate issues #20–#23.
- A self-service "promote to staff" flow — staff promotion is a deliberate manual action; bootstrap-only via CLI.
- 2FA / step-up auth for staff actions — separate epic if a customer requires it.
- Audit-log retention scrub UI for DPOs (curl-only for now; folds into the orgs/metrics/health epic if scope allows).
