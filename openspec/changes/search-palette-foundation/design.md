## Context

FastSaaS is a starter kit. Three foundation layers (identity, multi-tenancy + authz, audit) are explicit about not knowing the downstream domain — downstream products inherit by convention via `AuditedModel` mixin or explicit `audit.record(...)` calls. Search needs the same shape: the platform supplies a registry primitive + a single `/search` endpoint + a frontend palette; downstream products register one provider per entity type and one renderer per entity type, with no core patches.

The shape of the search problem matches audit's almost exactly: open `entity_type` vocabulary, capability gating per type, `app.current_org` tenant scope through RLS, an extension contract documented in a module-level `CLAUDE.md`. Where audit has two write paths (record / mixin), search has one read path (provider) — but the registry, naming, gating, and CLAUDE.md guidance all mirror.

## Goals

- Single `/search?q=` endpoint that aggregates results from any registered `SearchProvider`. No bespoke per-resource search routes.
- Open `entity_type` vocabulary keyed in module-scope registry. Adding a new entity = `register_provider(...)` at module load. No DB schema, no enum drift.
- Per-provider capability gate via `can(actor, op, resource_type, org_id, db, redis)` — already the only authz API. Provider declares the `(operation, resource_type)` pair as a class attribute.
- Tenant scope is a non-decision: `TenantContextDep` pins `app.current_org` before the orchestrator runs, so RLS scopes every provider's queries automatically.
- Frontend mirrors the contract: a `rendererRegistry: Map<entity_type, SearchResultRenderer>` per Shell. Adding a new entity = backend register + frontend register; no palette code changes.
- `backend/src/fastsaas/search/CLAUDE.md` is a first-class deliverable so a future Claude session in a downstream project can register a new provider correctly without reading the implementation.

## Non-goals

- Audit log search. Out of scope per the conversation; lands with a compliance-officer-facing admin page that handles PII presentation.
- Cross-workspace search.
- Fuzzy / typo-tolerant matching. ILIKE substring is v1.
- Indexed search infrastructure (`pg_trgm` / GIN / external). Defer until row counts justify.
- Per-Shell different *registries* sharing a single palette mount. Each Shell mounts its own palette; AppShell renders project/member, AdminShell renders org/metrics/etc when those land.
- AI-assisted natural-language queries.

## Decisions

### D1 — Registry pattern, not a `Search` Protocol-of-Protocols

`SearchProvider` is a Protocol class: `entity_type`, `label`, `capability_check`, `async search(...)`. Subclasses are stateless singletons; instantiation cost is zero. The registry is a module-scope `dict[str, SearchProvider]` keyed by `entity_type`. Registration happens at module-load time:

```python
# fastsaas/search/__init__.py
from fastsaas.search.registry import _PROVIDERS, register_provider
from fastsaas.search.providers.projects import ProjectSearchProvider
from fastsaas.search.providers.members import MemberSearchProvider

register_provider(ProjectSearchProvider())
register_provider(MemberSearchProvider())
```

Downstream products register on import of their own `search.py`:

```python
# apps/<saas>/src/<pkg>/search.py
from fastsaas.search import register_provider
from .scenarios import ScenarioSearchProvider

register_provider(ScenarioSearchProvider())
```

**Rationale.** Cheapest mechanism that meets the requirement. Mirrors `BUNDLES` in `authz/bundles.py` (module-scope dict) and `GLOBAL_REDACT` in `audit/redact.py` (module-scope frozenset). No DI container, no ABC, no metaclass — just Python.

### D2 — Capability gate is a class attribute, not a method

`SearchProvider.capability_check: tuple[Operation, ResourceType]`. The orchestrator runs `await can(actor, *provider.capability_check, org_id, db, redis)` once before invoking `provider.search(...)`. If False → skip, no result group emitted.

Alternative: provider has its own `async def can_search(...)` method. Rejected — couples gating logic to provider implementation; harder to grep for "all places that read members".

**Rationale.** Static metadata is enough; the gate is uniformly `(operation, resource_type, org_id)`. If a future provider needs custom gating (e.g. resource-scoped read), we extend with an optional method then. YAGNI now.

### D3 — Single `/search` endpoint, optional `kinds` filter

`GET /search?q=&kinds=projects,members` — `q` required (min 2 chars), `kinds` optional (CSV of entity types to query; default = all registered). Frontend doesn't pass `kinds` in v1; the param exists for future per-section search ("show me only members named Alice").

Wrapped by `TenantContextDep` so org-scoping is automatic. Returns:

```python
class SearchResponse(BaseModel):
    query: str
    groups: list[SearchGroup]

class SearchGroup(BaseModel):
    entity_type: str
    label: str
    hits: list[SearchHit]

class SearchHit(BaseModel):
    entity_type: str
    entity_id: UUID
    title: str            # primary display string
    subtitle: str | None  # optional second line (e.g. project slug, member email)
    href: str             # frontend route to navigate to
```

**Rationale.** Single endpoint = simpler caching, simpler frontend (one TanStack Query), simpler audit / logging surface. The `kinds` param keeps the door open for "search-on-this-tab" UX without splitting into per-resource routes.

### D4 — `SearchHit.href` server-rendered, not client-derived

The provider knows where the entity lives in the URL space (`/orgs/{slug}/projects/{projectSlug}` for project hits, `/orgs/{slug}/settings/members?focus={actorId}` for member hits — though the focus param is a future addition). Putting the path in the response means the frontend renderer is "render this string with this icon" without per-entity URL knowledge.

**Rationale.** Inversion: URLs are an entity concern, not a UI concern. Adding a new entity means the provider author writes the URL once; UI never needs an entity-aware switch.

### D5 — Provider runs in parallel via `asyncio.gather`

`search_all` collects providers that pass the `can()` gate, then `await asyncio.gather(*[p.search(...) for p in providers], return_exceptions=True)`. Exceptions in one provider don't fail the whole response — the failed group is omitted with a logged warning.

**Rationale.** N small queries in parallel is faster than N sequential. `return_exceptions=True` makes the search resilient to a buggy downstream provider — a search shouldn't 500 because some new `ScenarioSearchProvider` raised.

### D6 — ILIKE substring scan in v1

Every provider uses `column ILIKE '%' || :q || '%'`. No indexes added. At row counts <10k per workspace, the scan is sub-millisecond. The provider returns up to 10 hits; the orchestrator caps higher tiers if a future LIMIT-busting provider misbehaves.

**Rationale.** The cheapest correct solution. `pg_trgm` GIN indexes are a perf upgrade; they're free to add later because the API contract doesn't change.

### D7 — Frontend palette mounts inside `<Shell>`, not `__root.tsx`

Each Shell flavour (`<AppShell>`, `<AdminShell>`) mounts its own `<CommandPalette>` + `<CommandPaletteHotkey>`. AppShell registers project + member renderers + workspace-flavour Pages and Actions. AdminShell registers its own (empty in v1; plugged by #20).

Alternatives considered:
- **Single global palette in `__root.tsx`**: one keybind, one DOM node. Rejected because the registry composition would have to switch on URL pattern (am I in /admin or /orgs?), reintroducing the if/else we removed from the backend.
- **Per-route mounted palette**: too many mounts, redundant keybind handlers fighting for `⌘K`.

**Rationale.** Shell scope matches the registry scope. Shell already exists as the natural mount point.

### D8 — Recent searches per-workspace

`useRecentSearchesStore` is a Zustand persist store under `fastsaas.searches`. Internal shape: `{[slug: string]: string[]}` — last 10 distinct queries per slug. Reading the active list filters by `useOrgStore().currentOrgSlug`.

**Rationale.** Switching workspace shouldn't surface stale queries from another org. Per-workspace history makes the most-recent list relevant.

### D9 — shadcn `command` primitive added (`cmdk` dep)

`npx shadcn add command` adds `frontend/src/components/ui/command.tsx` and the `cmdk` dependency. Manual compose (Dialog + Input + filtered list) is doable but throws away the keyboard-nav / accessibility / virtual-list work shadcn already encapsulates.

**Rationale.** shadcn's `command` is the canonical pick; matches ADR-012 ("shadcn/ui canonical").

### D10 — `min_length` = 2 chars

Backend rejects `q.length < 2` with HTTP 400 `search.query_too_short`. Frontend short-circuits without firing a network request when input is < 2 chars. Single-char queries are noisy + run substring scans across every row in every provider.

**Rationale.** Cheap UX guardrail.

## Risks / trade-offs

- **Silent coverage gap**. If a downstream developer ships a new `table=True` class without registering a `SearchProvider`, search results are silently empty for that entity. Mitigated by `search/CLAUDE.md` (loaded into every Claude session) + ADR documentation. Mechanical guard (CI lint flagging unregistered table=True classes that handle user-facing data) is a follow-up — same kind of silent-coverage-gap risk audit has.

- **PII in titles / subtitles**. Provider authors might naively embed sensitive data in `SearchHit.title` ("Project: $top_secret_internal_name"). Mitigation: project / member / future providers explicitly limit `title` to columns explicitly named in their searchable-text section of `CLAUDE.md`. Audit-log search is excluded from v1 precisely because `intent_metadata.original_prompt` is unsuitable for free display.

- **Provider runtime budget**. A misbehaving downstream provider that does heavy joins could slow the whole `/search` response. Mitigation: `asyncio.gather` parallelises (so the slowest provider is the bottleneck, not the sum); future hard timeout per provider (`asyncio.wait_for(p.search(...), timeout=200ms)`) lands when the first slow provider appears.

- **Frontend renderer registry initialised at import time**. If a feature module is tree-shaken away because it's not imported, its renderer never registers, and a search hit of that entity_type falls through to a default "Unknown entity" row. Acceptable in v1 since foundation always imports project + member; downstream feature modules are imported at AppShell composition.

- **`q` param injection surface**. The query string flows to ILIKE via parameterised queries (SQLAlchemy `text(":q")` bind). No string concat. Documented as a hard rule in `CLAUDE.md`'s "What NOT to do" section.

## Migration plan

- No DB migration. No schema changes.
- Existing endpoints unchanged.
- Frontend `<SearchTrigger>` swaps from no-op to opening the palette. Existing keyboard shortcut hint (`⌘K` kbd) becomes functional.
- Foundation providers register on import of `fastsaas.search` — no opt-in needed by existing routes / services.
- Tests: provider-level unit tests (each provider against a seeded DB), service orchestrator test (capability skip / failed-provider tolerance), endpoint integration test (TenantContext + RLS + `q` validation), frontend palette smoke (open/close, type, navigate).

## Open questions

- **Should the palette also surface "Switch to project: alpha" actions when the user is in workspace context?** Tentative: yes — project hits already do that via `href`. Treat them as the same. Re-open if action-flavoured rows feel wrong inline with content rows.
- **How should an empty workspace render the palette?** Tentative: just Pages + Actions sections, with a hint "Type to search projects + members". Re-open if test users find it confusing.
- **Should the palette debounce input or fire-on-keystroke?** Tentative: fire on every keystroke ≥ 2 chars; TanStack Query's natural request dedup handles burst-typing. If perf issues surface, debounce 100ms.
- **Server-side recent-search persistence?** Defer.

## References

- Issue ganjasan/fastsaas#28.
- ADR-007 — multi-tenant isolation; RLS auto-scopes provider queries.
- ADR-010 — audit log shape; the registry pattern + CLAUDE.md extension contract are the model.
- ADR-013 — capabilities + bundles; per-provider `(operation, resource_type)` gate plugs into `can()`.
- `backend/src/fastsaas/audit/CLAUDE.md` — the prose template `search/CLAUDE.md` mirrors.
