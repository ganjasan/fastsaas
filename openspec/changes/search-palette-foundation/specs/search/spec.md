## ADDED Requirements

### Requirement: Foundation exposes a SearchProvider registry

The system SHALL provide a foundation module `fastsaas.search` exposing:

- A `SearchProvider` Protocol class with class attributes `entity_type: str`, `label: str`, `capability_check: tuple[Operation, ResourceType]`, and an `async def search(*, query, actor, org_id, limit, db) -> list[SearchHit]` method.
- A module-scope registry `_PROVIDERS: dict[str, SearchProvider]` keyed by `entity_type`, with public `register_provider(provider)` and `providers()` accessors.
- Pydantic response shapes `SearchHit`, `SearchGroup`, `SearchResponse`.

Foundation SHALL register two providers at module import: `ProjectSearchProvider` (entity_type `"project"`) and `MemberSearchProvider` (entity_type `"member"`).

#### Scenario: Foundation providers are registered on import

- **WHEN** `fastsaas.search` is imported
- **THEN** `providers()` returns at least two entries with `entity_type` equal to `"project"` and `"member"`

#### Scenario: Downstream package registers a new entity_type

- **GIVEN** a downstream package `apps.example.scenarios` defines `class ScenarioSearchProvider(SearchProvider)` with `entity_type = "scenario"`
- **WHEN** the downstream package imports and calls `register_provider(ScenarioSearchProvider())`
- **THEN** `providers()` includes the new provider keyed by `"scenario"`
- **AND** `GET /search?q=...&kinds=scenario` returns hits from that provider only

#### Scenario: entity_type collision is rejected

- **WHEN** `register_provider(...)` is called with an `entity_type` already in the registry
- **THEN** the call raises a clear error (`SearchProviderConflictError`) — registration is fail-loud, not silent overwrite

### Requirement: GET /search aggregates provider results, gated per-provider

The system SHALL expose `GET /search?q=&kinds=` wrapped by `TenantContextDep`. The endpoint SHALL:

1. Reject requests where `len(q) < 2` with HTTP 400 `code = "search.query_too_short"`.
2. Filter the registry by the optional `kinds` CSV (default = all registered providers).
3. For each surviving provider, run `await can(actor, *provider.capability_check, org_id, db, redis)`. Skip providers that fail the gate.
4. Run the surviving providers' `search(...)` calls in parallel via `asyncio.gather(..., return_exceptions=True)`. Exceptions in one provider SHALL NOT fail the whole response — the failing group is omitted with a logged warning.
5. Return `SearchResponse{query, groups: [{entity_type, label, hits}]}`. Groups with zero hits MAY be omitted.

#### Scenario: Member without read:project capability skips the project group

- **GIVEN** an actor with `role:viewer` (read:project on all org projects) — they have read:project
- **GIVEN** an actor with `role:guest_viewer` for one specific project — they only have read:project for resource_id, not type-wide
- **WHEN** the guest calls `GET /search?q=foo`
- **THEN** the response includes the `project` group only if the matched project's id is reachable to them (provider's query naturally filters by what the actor can read; capability gate type-wide check passes for any actor with at least one project capability)
- **AND** the `member` group is included only if the actor has `read:organisation`

#### Scenario: Query under min_length is rejected

- **WHEN** `GET /search?q=a` (single char) is called
- **THEN** the response is HTTP 400 with `code = "search.query_too_short"`

#### Scenario: Tenant scope is enforced via RLS

- **GIVEN** an actor is a member of org `acme` only
- **WHEN** they call `GET /search?q=alpha` and `acme` has a project with that name AND `globex` (a different org) has a project with that name
- **THEN** the response's `project` group includes only the `acme` project (RLS filters the second one because `app.current_org` is pinned to `acme.id`)

#### Scenario: A failing provider does not bring down the response

- **GIVEN** a downstream provider that raises an exception during search
- **WHEN** the endpoint runs
- **THEN** other groups are returned normally
- **AND** the failed provider's group is omitted
- **AND** a warning is logged with the provider's `entity_type`

### Requirement: ProjectSearchProvider matches name + slug + description

The system SHALL ship `ProjectSearchProvider` as a foundation provider:

- `entity_type = "project"`, `label = "Projects"`, `capability_check = (Operation.READ, ResourceType.PROJECT)`.
- Search query: `SELECT id, name, slug, description FROM projects WHERE deleted_at IS NULL AND (name ILIKE :q OR slug ILIKE :q OR description ILIKE :q) LIMIT :limit` — RLS auto-scopes to `app.current_org`.
- Each hit: `title = project.name`, `subtitle = project.slug`, `href = /orgs/{slug}/projects/{projectSlug}`.

#### Scenario: Project name matches case-insensitively

- **GIVEN** project `"Q4 Forecast"` in `acme`
- **WHEN** an `acme` member searches for `"q4"`
- **THEN** the project group contains a hit with `title = "Q4 Forecast"` and `href = "/orgs/acme/projects/q4-forecast"` (or whatever the actual slug is)

#### Scenario: Soft-deleted projects are excluded

- **GIVEN** a project with `deleted_at IS NOT NULL`
- **WHEN** a search query would otherwise match it
- **THEN** it is NOT returned

### Requirement: MemberSearchProvider matches user.email + actor.display_name

The system SHALL ship `MemberSearchProvider`:

- `entity_type = "member"`, `label = "Members"`, `capability_check = (Operation.READ, ResourceType.ORGANISATION)`.
- Joins `organisation_members` → `actors` → `users`, filters by the active org, ILIKE on `users.email` + `actors.display_name`.
- Each hit: `title = display_name`, `subtitle = email`, `href = /orgs/{slug}/settings/members`.

#### Scenario: Searching by display name surfaces the member

- **GIVEN** member with `display_name = "Maker"` and `email = "member@example.com"` in `acme`
- **WHEN** an `acme` member searches `"mak"`
- **THEN** the member group includes the hit

#### Scenario: Searching by email surfaces the member

- **WHEN** the same member searches `"@example.com"`
- **THEN** the member group includes hits for every member whose email contains the substring

#### Scenario: A guest (non-member) gets an empty member group

- **GIVEN** a `role:guest_viewer` actor (no `read:organisation` capability)
- **WHEN** they call `/search?q=anything`
- **THEN** the member group is omitted from the response (capability gate fails)
