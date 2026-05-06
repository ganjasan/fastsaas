---
title: Search palette ⌘K — foundation registry + project/member providers
status: in_progress
linked_issue: ganjasan/fastsaas#28
created: 2026-05-06
traces_to:
  adr:
    - "[[ADR-007_multi-tenant-isolation]]"
    - "[[ADR-010_audit-log-shape]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
  use_cases: []
  stakeholders: []
---

## Why

`<SearchTrigger>` (the `⌘K` button shipped in #24's Render-style chrome) is a placeholder no-op today. Filling it with a bespoke `if entity_type == "project" else if entity_type == "member"` endpoint would lock us into a closed taxonomy — every new domain entity (scenario, analysis, model run, …) would require a core patch to surface in search. That breaks the FastSaaS-as-starter-kit contract: the foundation must not know about downstream domains; downstream must extend by convention.

This change ships search as a **foundation primitive with an extension contract**, mirroring the `AuditedModel` / `record(...)` pattern. The contract:

- A `SearchProvider` Protocol class — downstream products implement one per entity type, register at module-load time, and the platform's `/search` endpoint orchestrates all registered providers in parallel with capability-gated filtering.
- An open `entity_type` vocabulary (lowercase singular noun) keyed in a module-scope registry, no DB schema. Foundation reserves `project`, `member`. Downstream picks `scenario`, `analysis`, `model_run` etc.
- Frontend mirrors the same shape: a `rendererRegistry: Map<entity_type, RowRenderer>` per Shell. Adding a new entity = backend `register_provider(...)` + frontend `rendererRegistry.set(...)`.
- `backend/src/fastsaas/search/CLAUDE.md` documents the contract for AI agents extending the platform — same flavour as `audit/CLAUDE.md`.

Without this, every new entity becomes a 3-file PR against the search palette. With it, downstream developers ship their entity's search alongside the entity itself.

## What changes

### Backend foundation

1. **New `fastsaas.search` module**:
   - `SearchProvider` Protocol — `entity_type`, `label`, `capability_check: tuple[Operation, ResourceType]`, `async search(...) -> list[SearchHit]`.
   - Module-scope registry `_PROVIDERS: dict[str, SearchProvider]` + `register_provider(p)` + `providers()` accessor.
   - `SearchHit`, `SearchGroup`, `SearchResponse` Pydantic models.
   - `service.search_all(actor, org_id, q, kinds, db, redis)` — orchestrator: capability-gates each provider, runs the surviving set in parallel via `asyncio.gather`, returns aggregated `SearchResponse`.

2. **Foundation providers** (registered at `search/__init__.py` import):
   - `ProjectSearchProvider` — entity_type `"project"`, label `"Projects"`, gate `(READ, PROJECT)`. ILIKE on `projects.name` + `slug` + `description`. RLS auto-scopes to `app.current_org`.
   - `MemberSearchProvider` — entity_type `"member"`, label `"Members"`, gate `(READ, ORGANISATION)`. ILIKE on `users.email` + `actors.display_name` joined to `organisation_members` for the active org.

3. **`GET /search?q=&kinds=`** route in `api/search.py`. Wrapped by `TenantContextDep` (so `app.current_org` is pinned + RLS works for free). Validates `q.length >= 2`. Optional `kinds` CSV filters which entity types to query.

4. **`backend/src/fastsaas/search/CLAUDE.md`** — extension contract for AI agents:
   - Decision tree (when to register a SearchProvider).
   - Recipe for adding a downstream entity provider (full code skeleton).
   - `entity_type` naming convention (lowercase singular noun, reserved core values listed).
   - Capability-gate guidance.
   - What NOT to do (parameterised queries only; never return PII; don't bypass `can()`).
   - Failure-mode note (silent gap if no provider registered for an entity, mirroring audit's silent-coverage-gap section).

### Frontend foundation

1. **`features/search/` module**:
   - `<CommandPalette>` — modal built on shadcn `command` primitive (added via `npx shadcn add command`).
   - `<CommandPaletteHotkey>` — global `⌘K` / `Ctrl+K` listener. Mounted inside `<Shell>` so each Shell flavour gets its own palette without polluting `__root.tsx`.
   - `rendererRegistry: Map<string, SearchResultRenderer>` — entity_type → icon + row renderer + onSelect handler.
   - `pagesRegistry`, `actionsRegistry` — static frontend lists for non-domain results (Overview / Projects / Settings nav, "Create project" / "Create organisation" / "Switch workspace" actions).
   - `useRecentSearchesStore` — Zustand persist under `fastsaas.searches`, filtered by active workspace slug; capped at 10 per workspace.
   - `<RowRenderer>` for project + member.

2. **AppShell + AdminShell wire-up**:
   - AppShell mounts `<CommandPalette>` + registers project/member renderers + workspace-flavour Pages and Actions.
   - AdminShell mounts its own `<CommandPalette>` instance with empty domain providers (placeholder until #20 ships orgs/metrics search). The same primitive — different registry composition.

3. **`<SearchTrigger>` becomes functional** — no longer a no-op; opens the palette via Shell context.

### Documentation

- `backend/src/fastsaas/search/CLAUDE.md` (Backend extension contract).
- `frontend/src/features/search/CLAUDE.md` (Frontend renderer registry contract).
- Update `CLAUDE.md` (root) to list `search/` alongside `audit/` as a foundation extension surface.

## What does NOT change

- The capability primitive (`can(...)`) — search providers consume it; they don't define new auth pathways.
- The `<Shell>` primitive — palette mounts inside; no chrome layout changes.
- Existing endpoints — `/search` is a new top-level route; no rewiring of `/orgs`, `/auth`, `/admin`.
- Audit log — searches don't audit (read-only operation).
- Recent searches in v1 are client-only (localStorage). Server-side recent-history is a follow-up.

## Out of scope

- **Audit search provider**. Compliance / DPO search across `audit_log` requires careful PII handling (`intent_metadata.original_prompt` is user-controlled text per #13) and a separate UI affordance. Lands when a compliance-officer-facing audit-reads admin page is built.
- **AdminShell domain providers**. AdminShell ships with the palette primitive but no domain providers in v1; #20 (orgs/metrics/health) plugs in admin-side providers.
- **Cross-workspace search**. Palette is always scoped to the pinned workspace.
- **Fuzzy / typo-tolerant matching**. ILIKE substring is v1; `pg_trgm` indexes land if performance demands.
- **Server-side recent-search history**. localStorage covers single-device use; cross-device sync is a follow-up.
- **AI-assisted search** ("show me everything Alice did last quarter"). Different epic.
- **Indexed search**. No GIN / pg_trgm / full-text in v1 — substring scan is fast at the row counts we expect.
