# Tasks — search-palette-foundation

Linked issue: ganjasan/fastsaas#28.

## 1. Backend foundation module

- [x] 1.1 Create `backend/src/fastsaas/search/` package with `__init__.py`, `models.py`, `registry.py`, `service.py`, `providers/{__init__,projects,members}.py`.
- [x] 1.2 `models.py` — `SearchHit(entity_type, entity_id, title, subtitle?, href)`, `SearchGroup(entity_type, label, hits)`, `SearchResponse(query, groups)`. All Pydantic v2 + ConfigDict.
- [x] 1.3 `registry.py` — `SearchProvider` Protocol with class attrs `entity_type`, `label`, and `async def is_visible(...)` + `async def search(*, query, actor, org_id, limit, db) -> list[SearchHit]`. Module-scope `_PROVIDERS: dict[str, SearchProvider]` + `register_provider(p)` + `providers()`. `register_provider` raises `SearchProviderConflictError` on duplicate `entity_type`. (Implementation diverged from the original `capability_check: tuple` plan — see design note 1.3 below.)
- [x] 1.4 `service.py::search_all(*, actor, org_id, is_guest, q, kinds, db, cache) -> SearchResponse`. Filters registry by kinds. Per-provider `is_visible` gate (sequential, exception-tolerant). `asyncio.gather(*tasks, return_exceptions=True)` — log + skip search exceptions, never propagate.
- [x] 1.5 `providers/projects.py::ProjectSearchProvider` — entity_type `"project"`. ILIKE on name/slug/description, `deleted_at IS NULL`. Joins `capabilities` on `(read, project)` + actor → caller sees only authorised rows; works for org members AND project-share guests. RLS auto-scopes via `app.current_org`. `href = /orgs/{slug}/projects/{projectSlug}`.
- [x] 1.6 `providers/members.py::MemberSearchProvider` — entity_type `"member"`, gate `(READ, ORGANISATION)`. JOIN organisation_members + actors + users; ILIKE on email + display_name. `href = /orgs/{slug}/settings/members`.
- [x] 1.7 Foundation provider auto-registration in `search/__init__.py` on import.

> **Design note (1.3):** the originally-planned `capability_check: tuple[Operation, ResourceType]` orchestrator-level gate doesn't compose with `scope=all_in_org` capabilities (one row per project, not one row per org). We replaced the tuple with `is_visible(...)` so each provider chooses the cheapest correct check — for `ResourceType.PROJECT` this is per-row JOIN with `capabilities`, for `ResourceType.ORGANISATION` it's a single `can()` call. Documented in `search/CLAUDE.md` as Patterns A / B / C.

## 2. API endpoint

- [x] 2.1 New router `backend/src/fastsaas/api/search.py`. `GET /orgs/{slug}/search?q=&kinds=` wrapped by `TenantContextDep` (path-scoped — TenantContextDep needs `slug` from the path).
- [x] 2.2 Handler delegates to `search_all` and returns the result. Explicit precondition check returns 400 `search.query_too_short` for `len(q) < 2`.
- [x] 2.3 Wire `search_router` into `main.py`.
- [x] 2.4 Run `pnpm codegen` so orval generates `useSearchEndpointOrgsSlugSearchGet` hook.

## 3. CLAUDE.md — extension contract for AI agents

- [x] 3.1 New `backend/src/fastsaas/search/CLAUDE.md` — decision tree, recipe with full code skeleton, `entity_type` naming convention, gate patterns A/B/C, tenant-scope automation, searchable-text guidance, what NOT to do, silent-coverage-gap warning.
- [x] 3.2 New `frontend/src/features/search/CLAUDE.md` — file inventory, recipes for adding renderer + Page + Action, conventions, what NOT to do.
- [x] 3.3 Update root `CLAUDE.md` — search promoted to fourth foundation layer; module-level guides cross-referenced; "Recipes" section gains the Search snippet; "must-not" list now mentions silent-coverage gap.

## 4. Frontend

- [x] 4.1 `pnpm add cmdk` + new `frontend/src/components/ui/command.tsx` (shadcn `command` primitive, `cmdk` under the hood).
- [x] 4.2 New `features/search/searchStore.ts` — Zustand persist `recentByWorkspace: Record<slug, SearchHit[]>` capped at 8 per workspace, with dedup-by-id float-to-top.
- [x] 4.3 New `features/search/registries/rendererRegistry.tsx` — `HitRenderer` type + module-scope Map + `registerRenderer(...)` + `renderHit(hit)` with fallback for unknown entity types and a console warning.
- [x] 4.4 `features/search/registries/{pagesRegistry,actionsRegistry}.ts` — typed shapes for Pages + Actions entries; foundation registers the AppShell pages (Projects / Members / Settings) and AdminShell pages (Orgs / Metrics / Health) on import.
- [x] 4.5 Renderer modules: `features/search/renderers/{projectRenderer,memberRenderer}.tsx`. Registered on import via `index.ts`.
- [x] 4.6 New `features/search/components/CommandPalette.tsx` — composes shadcn `<CommandDialog>` + `<CommandInput>` + `<CommandList>`. Renders Recent (if any + empty input), Pages (filtered by `visible(ctx)`), Actions (filtered), then backend groups (when q ≥ 2). Debounce 180ms; AbortSignal cancellation comes free with TanStack Query. Selection navigates via TanStack Router and closes the palette.
- [x] 4.7 New `features/search/components/CommandPaletteHotkey.tsx` — global window keydown listener. Opens palette on `Cmd+K` / `Ctrl+K`.
- [x] 4.8 `<SearchTrigger>` — wired to `useSearchStore.setOpen(true)`.
- [x] 4.9 AppShell + AdminShell each mount `<CommandPaletteHotkey>` + `<CommandPalette>`. Each shell passes its own `workspaceSlug` + `shell` flag so the visible Pages narrow appropriately.
- [x] 4.10 Wire orval-generated TanStack Query hook (`useSearchEndpointOrgsSlugSearchGet`) — fires when `q.length >= 2 && shell === "app"`; AbortSignal cancellation handled by TanStack Query.

## 5. Tests

- [x] 5.1 Backend unit — `registry.register_provider` rejects duplicate `entity_type` (`test_search_unit.py::TestRegistry`).
- [x] 5.2 Backend unit — `service.search_all` skips a provider whose `is_visible` returns False (`test_search_unit.py::TestServiceOrchestrator::test_provider_skipped_when_is_visible_returns_false`).
- [x] 5.3 Backend unit — `service.search_all` swallows a search exception and returns the rest; also handles is_visible exceptions (two tests in `TestServiceOrchestrator`).
- [x] 5.4 Backend integration — `GET /orgs/acme/search?q=forecast` as the org owner returns the matching project group with a usable href (`test_api_search.py::test_search_owner_finds_project`).
- [x] 5.5 Backend integration — `GET /orgs/acme/search?q=<email-prefix>` as owner surfaces the invited member; `kinds=project` narrows the response so member group is excluded (`test_search_owner_finds_member_by_email`, `test_search_kinds_filter_projects_only`).
- [x] 5.6 Backend integration — single-char `q` returns 400 `search.query_too_short` (`test_search_query_too_short_400`).
- [x] 5.7 Frontend smoke — `searchStore` dedup + per-workspace scoping + recents cap (`searchStore.test.ts`, 4 tests).
- [ ] 5.8 Frontend Playwright smoke — defer to manual smoke at PR review (palette open + type + select navigation). Foundation-lint guarantees component build.

## 6. Documentation alignment

- [x] 6.1 Root `CLAUDE.md` "Recipes" gains the "Add a SearchProvider for a new entity" snippet and points at the module guides.
- [x] 6.2 ADR mention — handled inside `design.md`; no new ADR (search lights up under ADR-013's capability primitive).

## 7. Validation + close-out

- [x] 7.1 `openspec validate search-palette-foundation --strict` passes.
- [x] 7.2 `cd backend && uv run ruff check .` clean.
- [x] 7.3 Full backend suite — 241 passed, no regression.
- [x] 7.4 `cd frontend && pnpm build && pnpm lint && pnpm test --run` — build clean, lint clean, vitest 70/70.
- [ ] 7.5 Manual smoke via Playwright — at PR review.
- [ ] 7.6 PR opened, linked to issue #28.
- [ ] 7.7 Archive change after merge; sync delta specs to `openspec/specs/search/spec.md` (new) + `openspec/specs/design-system/spec.md`.
