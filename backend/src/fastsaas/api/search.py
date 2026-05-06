"""GET /search — workspace-scoped, capability-gated, provider-aggregated.

The route is wrapped by `TenantContextDep` so `app.current_org` is pinned
before any provider runs. RLS does the rest of tenant scoping.

Single endpoint, no per-resource splits — see design.md D3 for rationale.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import SessionDep
from fastsaas.search import SearchResponse, search_all
from fastsaas.tenants.dependencies import TenantContextDep

router = APIRouter(prefix="/orgs/{slug}", tags=["search"])

_MIN_QUERY_LEN = 2


@router.get("/search", response_model=SearchResponse)
async def search_endpoint(
    ctx: TenantContextDep,
    db: SessionDep,
    q: Annotated[str, Query(description="Substring query — minimum 2 characters")],
    kinds: Annotated[
        str | None,
        Query(
            description=(
                "Comma-separated list of entity_types to query "
                "(e.g. `projects,members`). Default: all registered."
            ),
        ),
    ] = None,
) -> SearchResponse:
    """Aggregate search across all registered SearchProviders for the
    actor's active workspace. Each provider is gated through `can()`
    using its declared `(operation, resource_type)`; failed gate → group
    omitted. A provider raising during search → group omitted (with a
    server-side warning); the rest of the response returns normally.
    """
    if len(q) < _MIN_QUERY_LEN:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "search.query_too_short",
                "message": f"`q` must be at least {_MIN_QUERY_LEN} characters",
            },
        )

    kinds_list = (
        [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    )
    return await search_all(
        actor=ctx.actor,
        org_id=ctx.org.id,
        is_guest=ctx.is_guest,
        q=q,
        kinds=kinds_list,
        db=db,
        cache=get_redis(),
    )
