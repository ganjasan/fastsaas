"""FastAPI dependencies that gate routes on a capability check.

Usage in a route:

    @router.post(
        "/orgs/{slug}/projects",
        dependencies=[Depends(require_capability("write", "project"))],
    )
    async def create_project(...): ...

The dependency composes `current_actor` (identity middleware dependency) and
`get_session` (per-request transactional session) and resolves `resource_id`
from a path parameter when configured — when the route uses `{slug}` only the
check is type-wide; when the route includes a UUID path param the dependency
resolves it before calling `can(...)`.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from fastsaas.authz.bundles import Operation, ResourceType
from fastsaas.authz.check import can
from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import SessionDep, current_actor
from fastsaas.identity.schemas import CurrentActor


def require_capability(
    operation: str,
    resource_type: str,
    *,
    resource_id_param: str | None = None,
):
    """Build a FastAPI dependency that runs `can(...)` for the request.

    `resource_id_param` is the name of a path parameter holding a UUID resource
    id (e.g. `"project_id"`); leave `None` for type-wide checks.
    """
    op = Operation(operation)
    rt = ResourceType(resource_type)

    async def dep(
        request: Request,
        actor: Annotated[CurrentActor, Depends(current_actor)],
        db: SessionDep,
    ) -> None:
        resource_id: UUID | None = None
        if resource_id_param is not None:
            raw = request.path_params.get(resource_id_param)
            if raw is not None:
                try:
                    resource_id = UUID(str(raw))
                except ValueError as exc:
                    raise HTTPException(
                        status.HTTP_404_NOT_FOUND,
                        detail={"code": "resource.not_found"},
                    ) from exc

        cache = get_redis()
        ok = await can(actor.id, op, rt, resource_id, db=db, cache=cache)
        if not ok:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"code": "authz.forbidden"},
            )

    return dep
