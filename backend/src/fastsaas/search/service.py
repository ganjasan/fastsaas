"""Search orchestrator — gated by per-provider `is_visible`, parallel,
fault-tolerant.

`search_all` runs every registered provider whose `is_visible(...)`
returns True, in parallel via `asyncio.gather(..., return_exceptions=True)`.
A provider that raises is logged + omitted; the rest of the response is
returned normally. A provider that returns zero hits is omitted from the
response (no empty groups).
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.identity.schemas import CurrentActor
from fastsaas.search.models import SearchGroup, SearchHit, SearchResponse
from fastsaas.search.registry import SearchProvider, providers

_log = logging.getLogger(__name__)

PER_PROVIDER_LIMIT = 10


async def search_all(
    *,
    actor: CurrentActor,
    org_id: UUID,
    is_guest: bool,
    q: str,
    kinds: list[str] | None,
    db: AsyncSession,
    cache: Redis | None,
) -> SearchResponse:
    """Aggregate results across providers; ask each for `is_visible(...)`."""
    candidates = providers()
    if kinds is not None:
        kind_set = {k.strip() for k in kinds if k.strip()}
        candidates = [p for p in candidates if p.entity_type in kind_set]

    # Visibility gate per provider — sequentially (each call shares the db
    # session). Errors here treat the provider as not-visible and skip it.
    surviving: list[SearchProvider] = []
    for provider in candidates:
        try:
            visible = await provider.is_visible(
                actor=actor,
                org_id=org_id,
                is_guest=is_guest,
                db=db,
                cache=cache,
            )
        except Exception as exc:
            _log.warning(
                "search provider %r is_visible() raised %s: %s — skipping",
                provider.entity_type,
                type(exc).__name__,
                exc,
            )
            continue
        if visible:
            surviving.append(provider)

    if not surviving:
        return SearchResponse(query=q, groups=[])

    # Run the surviving providers in parallel; tolerate per-provider failures.
    tasks = [
        provider.search(
            query=q,
            actor=actor,
            org_id=org_id,
            limit=PER_PROVIDER_LIMIT,
            db=db,
        )
        for provider in surviving
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    groups: list[SearchGroup] = []
    for provider, result in zip(surviving, results, strict=True):
        if isinstance(result, BaseException):
            _log.warning(
                "search provider %r raised %s: %s — group omitted",
                provider.entity_type,
                type(result).__name__,
                result,
            )
            continue
        hits: list[SearchHit] = list(result)
        if not hits:
            continue
        groups.append(
            SearchGroup(
                entity_type=provider.entity_type,
                label=provider.label,
                hits=hits[:PER_PROVIDER_LIMIT],
            )
        )

    return SearchResponse(query=q, groups=groups)
