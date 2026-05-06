# CLAUDE.md — `search/`

This module is FastSaaS's fourth foundation primitive. Every domain
entity in the platform — core or downstream — that an end-user might
want to find via the `⌘K` palette must register a `SearchProvider`. This
file is the contract every PR that adds a user-facing entity has to
honour.

Read ADR-013 (capability primitive) and `audit/CLAUDE.md` (the registry
+ extension contract that this module mirrors) before changing anything
in this directory.

## Decision tree — register a SearchProvider, or not?

```
Are you adding a new SQLModel `table=True` class that an end-user might
search for by name, slug, email, label, or any human-readable column?
├── Yes → Register a SearchProvider for it.
│         The user expects to type its name into ⌘K and find it.
│         Skipping silently breaks the search palette for that entity
│         type — same kind of silent coverage gap as forgetting
│         AuditedModel on a domain table.
└── No  → Skip.
          Internal cache rows, junction tables, audit_log itself
          (separate compliance-officer surface), capability rows (never
          exposed) — none of these get a provider.
```

## Recipe — add a downstream entity provider

```python
# In your downstream package:
# apps/<your-saas>/src/<pkg>/search.py
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.authz.models import Capability
from fastsaas.identity.schemas import CurrentActor
from fastsaas.search import SearchHit, SearchProvider, register_provider

from .models import Scenario  # your domain entity


class ScenarioSearchProvider:
    entity_type = "scenario"  # lowercase, singular, noun
    label = "Scenarios"        # rendered in the palette section header

    async def is_visible(
        self,
        *,
        actor: CurrentActor,
        org_id: UUID,
        is_guest: bool,
        db: AsyncSession,
        cache: Redis | None,
    ) -> bool:
        # Choose the gate that fits your bundle's scope (see "Gate guidance").
        # Org-wide capabilities use can(...resource_type, org_id):
        return await can(
            actor.actor_id,
            Operation.READ,
            ResourceType.SCENARIO,
            org_id,
            db=db,
            cache=cache,
        )

    async def search(
        self,
        *,
        query: str,
        actor: CurrentActor,
        org_id: UUID,
        limit: int,
        db: AsyncSession,
    ) -> list[SearchHit]:
        like = f"%{query}%"
        stmt = (
            select(Scenario.id, Scenario.name, Scenario.slug)
            .where(
                Scenario.deleted_at.is_(None),
                or_(Scenario.name.ilike(like), Scenario.slug.ilike(like)),
            )
            .order_by(Scenario.name.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            SearchHit(
                entity_type=self.entity_type,
                entity_id=row.id,
                title=row.name,
                subtitle=row.slug,
                href=f"/orgs/{org_slug}/scenarios/{row.slug}",
            )
            for row in rows
        ]


# Register at module import — same pattern as `BUNDLES` in
# `authz/bundles.py`. Call once; the registry rejects duplicates.
register_provider(ScenarioSearchProvider())
```

That's it. Once your domain package is imported by the app's startup
(usually via the main router or a feature index), the orchestrator at
`/orgs/{slug}/search` finds your provider, asks `is_visible()` whether
it should run, and includes its hits alongside core providers. The
frontend renderer registry needs a matching entry — see
`frontend/src/features/search/CLAUDE.md`.

### `entity_type` naming convention

`SearchProvider.entity_type` keys the registry. Convention enforced by
code review:

- **lowercase, singular, noun**: `scenario`, `analysis`, `property`,
  `model_run`. NOT `Scenarios`, `created_scenario`, `Scenario_v2`.
- **Reserved foundation values** — do NOT shadow:
  `project`, `member`. The registry itself raises
  `SearchProviderConflictError` if you try.
- Use the same string you use for `audit_log.entity_type`. Filter
  queries against audit reads stay uniform across core and downstream.

### Gate guidance — `is_visible(...)` patterns

The orchestrator asks every provider whether it should run for the
current caller. Pick the cheapest correct check:

**Pattern A — org-scoped capability**

For resource types whose bundle templates use `scope=self` (i.e. one cap
per org keyed on `resource_id = org_id`):

```python
async def is_visible(self, *, actor, org_id, is_guest, db, cache) -> bool:
    return await can(
        actor.actor_id, Operation.READ, ResourceType.AUDIT_LOG, org_id,
        db=db, cache=cache,
    )
```

This cleanly excludes guests (they don't hold org-wide reads) and any
member whose role doesn't include the cap.

**Pattern B — per-resource capability + JOIN-time filter**

For resource types whose bundle templates use `scope=all_in_org` or
`scope=resource` (one row per project, per shared resource, etc.) —
e.g. `project`. There's no "is the actor allowed to search projects?"
question that's cheaper than the search itself. Set `is_visible` to
return True (the route already enforced workspace access via
`TenantContextDep`) and JOIN `capabilities` inside the query so each
caller sees only the rows they hold a `(read, <type>)` cap for. See
`providers/projects.py` for the canonical implementation.

**Pattern C — members-only**

Strictly for org members, never for guests:

```python
async def is_visible(self, *, actor, org_id, is_guest, db, cache) -> bool:
    if is_guest:
        return False
    return await can(
        actor.actor_id, Operation.READ, ResourceType.ORGANISATION, org_id,
        db=db, cache=cache,
    )
```

The `(READ, ORGANISATION, org_id)` check alone is already false for
guests, so the explicit `is_guest` short-circuit is just for clarity
when the intent is "internal directory".

Don't invent new operations just for search. Reuse the bundle vocabulary.

### Tenant scope is automatic

The `/orgs/{slug}/search` route is wrapped by `TenantContextDep`, which
pins `app.current_org` AND `app.current_actor` for the `app_user`
session before your provider runs. Every query you write naturally
scopes via Postgres RLS — you don't add `WHERE organisation_id = :org_id`
for tables that already have RLS policies. For tables that DON'T have
org-scoped RLS (notably the `actors` + `users` join target), filter
explicitly via a JOIN to `organisation_members`, the way
`MemberSearchProvider` does.

The `app.current_actor` pin also enables the `actor_self_read` policy on
`capabilities`, which is what makes Pattern B's JOIN against the caps
table work without BYPASSRLS.

**Do NOT use `migrator_session_scope()` from inside a provider.** That
session has BYPASSRLS — would leak cross-tenant data. The `db` parameter
the orchestrator passes you is already the tenant-pinned session.

### Searchable text — what's safe?

| Column kind | Safe in `title` / `subtitle`? |
|---|---|
| Org-scoped name / slug / description | ✓ |
| `User.email` / `Actor.display_name` (member-rendered) | ✓ — caller already has `read:organisation` |
| `intent_metadata.original_prompt` (audit) | ✗ — user-typed PII per #13. Audit search lives in a separate admin surface |
| `password_hash` / `token_hash` / any redact-listed column | ✗ — never |
| `actor_id` raw UUID | OK as `entity_id` (machine-readable); never as a `title` (humans don't read UUIDs) |

## Reading `/orgs/{slug}/search`

The endpoint returns one `SearchResponse{query, groups[]}` envelope.
Each group has `entity_type`, `label`, and up to `limit` (10) hits.
Frontend palette renders rows by looking up the renderer registered for
each `entity_type` — unknown types fall back to a default renderer with
a console warning, so a backend-only PR that adds a new provider
without a matching frontend renderer ships gracefully (the entries are
still navigable; they just look generic).

### Untrusted strings on the read side

`SearchHit.title` and `subtitle` come straight from your provider, which
in turn pulls them from your tables. If your domain ever stores
user-controlled text in those columns (project descriptions, scenario
names, etc.), you have two choices:

1. **Don't surface those columns in search.** If the column is
   user-typed prose without length / character validation, prefer not
   to put it in `title`/`subtitle`.
2. **Trust your column-level validation.** If your feature already
   validates on insert (e.g. project name is a single-line string with
   a length cap), search inherits that safety.

Frontend renders these strings via React's text-content escaping by
default — there's no innerHTML path. That handles XSS. But truncation,
length caps, and "is this column appropriate for free display" are your
provider's responsibility.

## What NOT to do

- **Do NOT bypass `is_visible`** with provider-level "I'll just gate
  inside `search()`" assumptions. The orchestrator uses `is_visible` as
  the canonical "should this provider run" signal — telemetry, future
  caching, and cost shaping all hang off it. Keep the gate explicit.
- **Do NOT call `can()` repeatedly per row.** Pattern B replaces a
  per-row `can()` call with a JOIN against `capabilities`; that's an
  O(1) extra join, not an O(n) capability lookup.
- **Do NOT string-concat the query into SQL.** Use parameterised
  queries — `column.ilike(f"%{query}%")` is fine because SQLAlchemy
  parameterises it; raw `text(f"... ILIKE '%{query}%' ...")` is a SQL
  injection.
- **Do NOT return more than `limit` hits.** The orchestrator passes a
  cap; respect it. Returning more wastes bandwidth and slows the
  response by an unbounded factor.
- **Do NOT surface PII in `title` or `subtitle`** — IPs, raw prompts,
  hashed tokens, anything from `audit_log.intent_metadata`. The palette
  renders those fields verbatim.
- **Do NOT register at request time.** Module-load only. Registration
  is process-global; calling `register_provider(...)` from a route
  handler would race with itself across worker processes and only
  register on whichever worker hit it first.
- **Do NOT use `migrator_session_scope()` from a provider.** BYPASSRLS
  → cross-tenant leak. The `db` parameter is already tenant-pinned.
- **Do NOT silently skip on operations that "feel like search but
  aren't".** Background jobs producing dashboards, periodic enrichment
  workers, future AI-assisted query expansion — none of those go
  through `SearchProvider`. This module is strictly for the user-facing
  ⌘K palette.

## Failure mode — silent coverage gap

If a downstream developer ships a new `table=True` class without
registering a `SearchProvider`, search results are silently absent for
that entity. There is no compile-time signal of "you forgot search".
Mitigations:

- This file is loaded into context for every Claude Code session in
  this repo or its forks.
- A CI check that warns when a new `table=True` class doesn't have a
  matching `SearchProvider` is tracked as backlog (would close the gap
  mechanically — same flavour as the audit-coverage CI lint in #14).

If you're shipping a new downstream domain table and you're not sure
whether to add a `SearchProvider`: **the answer is yes**. The
constructor cost is zero; the registry is a dict; the orchestrator runs
in parallel. If the entity should never be searchable (caches, scratch),
note that explicitly in the model docstring so the next reader knows
the omission was deliberate.
