"""FastAPI dependency that gates a route on platform-staff authority.

Calls `can(actor, PLATFORM_ADMIN, PLATFORM)` which short-circuits to
`actors.is_platform_staff`. Raises 403 `authz.forbidden` on miss.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import SessionDep, current_actor
from fastsaas.identity.schemas import CurrentActor


async def require_platform_staff(
    actor: Annotated[CurrentActor, Depends(current_actor)],
    db: SessionDep,
) -> CurrentActor:
    ok = await can(
        actor.actor_id,
        Operation.PLATFORM_ADMIN,
        ResourceType.PLATFORM,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )
    return actor


PlatformStaffDep = Annotated[CurrentActor, Depends(require_platform_staff)]
