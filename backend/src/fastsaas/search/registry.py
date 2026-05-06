"""Search provider Protocol + module-scope registry.

Foundation primitive — same flavour as `audit/__init__.py`'s `record(...)`
or the `BUNDLES` dict in `authz/bundles.py`. Downstream products extend
the platform's search by registering one `SearchProvider` per
domain entity (scenarios, analyses, model runs, …). The orchestrator in
`service.py` iterates `_PROVIDERS`, asks each provider whether it should
run, and parallelises the surviving search calls via `asyncio.gather`.

Registration is process-global: providers register at module import,
never per-request. See `search/CLAUDE.md` for the recipe.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.identity.schemas import CurrentActor
from fastsaas.search.models import SearchHit


class SearchProviderConflictError(Exception):
    """Raised when `register_provider` is called with an `entity_type`
    that already has a registered provider. Registration is fail-loud:
    silent overwrite would mask a downstream bug where two modules race
    to claim the same key."""


@runtime_checkable
class SearchProvider(Protocol):
    """Contract for one entity type's search results.

    Implementations are stateless singletons.

    Authorization: each provider is responsible for its own gating. The
    orchestrator calls `is_visible(...)` once per request and skips the
    provider entirely if it returns False. For per-row visibility
    (e.g. project shares grant access to one row of a table), the
    provider's `search` query JOINs `capabilities` to filter accessible
    rows. The route already pins `app.current_org` via TenantContextDep
    so RLS handles tenant scoping; providers do NOT add `WHERE
    organisation_id = ?` clauses to RLS-policed tables.
    """

    entity_type: str
    label: str

    async def is_visible(
        self,
        *,
        actor: CurrentActor,
        org_id: UUID,
        is_guest: bool,
        db: AsyncSession,
        cache: Redis | None,
    ) -> bool:
        """Cheap gate — should this provider run for this caller?

        Default in foundation providers: members + guests for project,
        members-only for member. Downstream providers typically call
        `await can(actor.actor_id, READ, <resource_type>, org_id, ...)`
        when their resource type has org-wide caps (scope=self), or
        return True and self-filter rows when capabilities are
        per-resource (scope=all_in_org / resource).
        """
        ...

    async def search(
        self,
        *,
        query: str,
        actor: CurrentActor,
        org_id: UUID,
        limit: int,
        db: AsyncSession,
    ) -> list[SearchHit]: ...


_PROVIDERS: dict[str, SearchProvider] = {}


def register_provider(provider: SearchProvider) -> None:
    """Register a provider keyed on its `entity_type`.

    Raises `SearchProviderConflictError` if the key is already taken.
    """
    key = provider.entity_type
    if key in _PROVIDERS:
        raise SearchProviderConflictError(
            f"SearchProvider for entity_type {key!r} is already registered "
            f"(existing: {type(_PROVIDERS[key]).__name__}, "
            f"new: {type(provider).__name__})"
        )
    _PROVIDERS[key] = provider


def providers() -> list[SearchProvider]:
    """Snapshot of currently registered providers, in registration order."""
    return list(_PROVIDERS.values())


def _reset_for_tests() -> None:
    """Test-only helper. NOT exposed in `search/__init__.py`'s public surface
    — production code MUST NOT clear the registry mid-process."""
    _PROVIDERS.clear()
