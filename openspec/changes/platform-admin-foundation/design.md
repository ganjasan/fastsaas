## Context

The org-level capability model (ADR-013) was designed for tenant-scoped grants: bundles are minted per-org, capabilities reference an `organisation_id`, RLS uses `app.current_org`. That model breaks down for platform-level operations: a "platform admin" by definition acts cross-org, and minting a per-org bundle to every existing org is both noisy and brittle (new orgs would need a fan-out).

ADR-009 anchors the actor model (CTI: HUMAN/AGENT/SERVICE). Platform staff is a property of an actor regardless of which org(s) they belong to. The cleanest model: a column on `actors` that names them.

## Goals

- One bit on `actors` says "this actor is platform staff". Toggleable out-of-band.
- Routes still go through `can()`; no second authz primitive for callers to remember.
- Org-scoped reads / writes are unchanged; staff is purely additive.
- Frontend admin shell is a fully separate route tree; non-staff users hit `/admin/*` and get 403 + redirect.

## Non-goals

- Replacing the bundle model. Org-level authz stays bundle-driven.
- Building real admin pages. Each subsequent epic ships one.
- Multi-tier staff (e.g. "read-only support" vs "full admin"). Phase 1 is a single bit; granular roles are a separate epic if a real customer asks.
- A UI for promoting staff. Bootstrap-only.

## Decisions

### D1 — A boolean column on `actors`, not a separate `platform_staff` table

Adding `actors.is_platform_staff BOOLEAN NOT NULL DEFAULT FALSE` is a one-line migration and lets `can()` short-circuit without a join. The alternative — a separate `platform_staff` table — adds a join on every staff check and a referential integrity dance that nothing else benefits from. The flag never accumulates tiered metadata in v1; if it ever needs to (e.g. "scoped staff who only see EU orgs"), that's a new table at that point.

**Rationale.** Cheapest change that meets the requirement; trivially extensible if the model needs to broaden later.

### D2 — `can()` short-circuits `(PLATFORM_ADMIN, PLATFORM)` against the flag

The "capability is the only authz API" rule (root `CLAUDE.md` §"Architectural rules") says routes call `can()`. To honour it without inflating the capabilities table with platform-staff rows, `can()` itself checks the flag when `resource_type == PLATFORM`. The capability table stays org-scoped; the flag is the authority record for platform.

```python
async def can(actor_id, operation, resource_type, resource_id=None, *, db, cache=None):
    if resource_type in (ResourceType.PLATFORM, "platform"):
        return await _is_platform_staff(actor_id, db=db)
    # ... existing logic
```

`_is_platform_staff` reads `actors.is_platform_staff` for the actor. RLS on `actors` (already scoped to self-read via `app.current_actor`) suffices.

**Rationale.** Keeps the public `can()` surface uniform. No new authz primitive for routes / services to learn.

### D3 — One operation `PLATFORM_ADMIN`, not separate `READ` / `WRITE` / `DELETE`

Phase 1 ships a single bit; the API surface doesn't need finer ops yet. When the orgs-and-metrics epic lands, every endpoint there asks `can(actor, PLATFORM_ADMIN, PLATFORM)` and that's the gate. If a sub-role distinction emerges later, we can split the operation; until then the simpler model wins.

**Rationale.** Avoids inventing a finer-grained taxonomy before any consumer needs it.

### D4 — Promotion is CLI-only via `make seed-platform-staff`

A self-service "promote to staff" flow would need its own admin UI gated on… platform staff (chicken-and-egg) or on the very first user (which is brittle and tied to deployment order). The seed CLI sidesteps both:

```bash
make seed-platform-staff USER_EMAIL=alice@example.com
# under the hood: uv run python -m fastsaas.scripts.seed_platform_staff alice@example.com
```

The script does a single `UPDATE actors SET is_platform_staff = TRUE WHERE id = (...)` through the migrator session. Rejects unknown emails. Audited via a regular `audit_log` row (`entity_type = "actor"`, `action = "update"`, `diff` showing the flag flip).

For staff-to-staff promotion (a real platform-staff actor promoting another), an in-UI flow can land later; v1 is bootstrap.

**Rationale.** Eliminates the chicken-and-egg; the CLI is auditable; one less attack surface than a route.

### D5 — Admin frontend is a separate route tree, not under `/orgs/{slug}/admin`

`/admin/*` lives at the URL root, parallel to `/orgs/*`. Pinning a slug into the URL would suggest org-scoped admin (which is the existing Settings); the platform admin is explicitly cross-org and shouldn't be confused with it.

The shell is `routes/admin.tsx` (parent layout) + `routes/admin.<section>.tsx` for each section. Auth-redirect: every `admin.*` route checks `useAdminMe` (calling `/api/admin/me`) and redirects to `/auth/login` for unauthenticated, `/orgs` for non-staff authenticated.

**Rationale.** URL clarity: `/admin/orgs` is platform-staff "list every org"; `/orgs/{slug}/settings` is "this org's settings". Conflating them invites permission-confusion.

### D6 — Admin shell does NOT inherit the org-theme provider; uses a fixed neutral theme

The org's branding is for org members. Platform staff sees a neutral, unbranded interface so it's visually distinct from any one org's surface. This also avoids the auth/refresh cycle of "which org's theme should the shell use" when the staff member belongs to multiple orgs (or none).

The fixed theme is the `default` preset hard-coded inline in `<AdminShell>`. Light/dark toggle still works (per-user, same store as the dashboard).

**Rationale.** Visual disambiguation between org admin and platform admin. Eliminates a coupling to issue #5's ThemeProvider that would otherwise force ordering between PRs.

### D7 — Placeholder pages now; one sub-issue replaces each

Each section sub-route renders a `<Card>` with title + "Coming soon — see issue #N" copy. This way the route tree, sidebar nav, and capability gates ship today; subsequent epics swap one placeholder at a time without restructuring.

**Rationale.** Foundation epic is meaningful (a staff member can land on /admin and see the shape of the platform) without forcing the work of any individual section into this PR.

## Risks / trade-offs

- **Bootstrap requires DB write access.** A platform deployment without a console flips its first staff via the seed script run on the host. Acceptable for the solo-dev / SMB SaaS shape.
- **Flag drift between actors and bundles.** A platform-staff actor still belongs to orgs as a normal member. If a future bug clears the flag without revoking org bundles, the actor stays org-functional but loses platform access — same blast radius as any single-actor account problem.
- **`can()` complexity grows.** Each new resource type in `can()` adds a branch. Acceptable while the count is small (3 today: org-level types, audit_log, platform); revisit if it crosses ~6.
- **Visual disambiguation depends on operator habit.** A staff member could mistake the admin surface for an org dashboard if they don't notice the URL. Mitigated by D6 (neutral theme) and a "PLATFORM ADMIN" label in the shell header.

## Migration plan

- Migration 0008 adds the column with default FALSE — every existing row stays non-staff. No data migration.
- After deployment, the operator runs `make seed-platform-staff USER_EMAIL=<their-email>` to bootstrap the first staff. From that point on, all platform-level work flows through the new shell.
- Subsequent epics (#20–#23) each ship their own migration (e.g. `platform_config` table for #21/#23) without touching `actors` again.

## Open questions

- **Q: Should `can(actor, PLATFORM_ADMIN, PLATFORM)` log an attempt-line for non-staff?** Tentative: yes, the existing audit-log path covers any side-effecting denial; pure read-checks are noise. Re-open if compliance asks.
- **Q: Can a platform-staff actor be deleted (org-level)?** Tentative: deleting an Actor with `is_platform_staff=TRUE` should require explicit confirmation (or be barred entirely; no v1 enforcement, just a CLAUDE.md warning).
- **Q: Should the AdminShell live behind `/admin` or a subdomain (`admin.fastsaas.dev`)?** Subdomain feels heavyweight for v1; revisit if there's an attack-surface argument (e.g. SameSite cookie tricks).

## References

- Issue ganjasan/fastsaas#19.
- ADR-009 (actor CTI model) — extended.
- ADR-013 (capabilities + bundles) — preserved verbatim for org-level.
- ADR-007 (multi-tenant isolation) — admin reads use the migrator session, same pattern as compliance officer GUC reads.
- Sibling issues #20–#23 plug into the shell built here.
