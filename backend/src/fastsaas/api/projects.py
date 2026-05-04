"""Project endpoints under `/orgs/{slug}/projects/...` (issue #3, phase 7).

Authorisation:
- POST   /orgs/{slug}/projects                        — create new project;
                                                         gated on
                                                         `can(admin, organisation, org.id)`
                                                         because the project
                                                         doesn't exist yet,
                                                         so resource-level
                                                         project capabilities
                                                         can't be checked.
- GET    /orgs/{slug}/projects                        — list visible to
                                                         caller. Members see
                                                         all; guests see only
                                                         the projects they
                                                         hold a `read:project`
                                                         capability for.
- GET    /orgs/{slug}/projects/{project_slug}         — `can(read, project, project.id)`.
- PATCH  /orgs/{slug}/projects/{project_slug}         — `can(write, project, project.id)`.
- DELETE /orgs/{slug}/projects/{project_slug}         — `can(admin, project, project.id)`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.authz.check import _load_active_capabilities
from fastsaas.cache.redis import get_redis
from fastsaas.identity.email import send_project_share
from fastsaas.identity.middleware import (
    SessionDep,
    current_actor,
    require_verified_email,
)
from fastsaas.identity.schemas import CurrentActor
from fastsaas.tenants.dependencies import (
    ProjectContextDep,
    TenantContextDep,
)
from fastsaas.tenants.schemas import (
    AcceptShareRequest,
    AcceptShareResponse,
    ProjectCreateRequest,
    ProjectListItem,
    ProjectRead,
    ProjectShareItem,
    ProjectShareRequest,
    ProjectShareResponse,
    ProjectUpdateRequest,
)
from fastsaas.tenants.service import (
    ProjectNotFoundError,
    ProjectService,
    ProjectShareService,
    ProjectSlugTakenError,
    ShareNotFoundError,
    ShareTTLError,
)
from fastsaas.tenants.slugs import SlugError, validate_slug

router = APIRouter(prefix="/orgs/{slug}/projects", tags=["projects"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectRead,
    dependencies=[Depends(require_verified_email)],
)
async def create_project(
    body: ProjectCreateRequest,
    ctx: TenantContextDep,
    db: SessionDep,
) -> ProjectRead:
    try:
        validate_slug(body.slug, kind="project")
    except SlugError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.code, "message": str(e)},
        ) from e

    if ctx.is_guest:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    ok = await can(
        ctx.actor.actor_id,
        Operation.ADMIN,
        ResourceType.ORGANISATION,
        ctx.org.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    try:
        project = await ProjectService.create(
            org_id=ctx.org.id,
            name=body.name,
            slug=body.slug,
            description=body.description,
            created_by=ctx.actor.actor_id,
        )
    except ProjectSlugTakenError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "project.slug_taken"},
        ) from e
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    ctx: TenantContextDep, db: SessionDep
) -> list[ProjectListItem]:
    projects = await ProjectService.list_in_org(ctx.org.id)
    if not ctx.is_guest:
        return [ProjectListItem.model_validate(p) for p in projects]

    # Guests see only the projects they hold an active read capability for.
    # Single capability load up front; filter in Python — N is small per org.
    caps = await _load_active_capabilities(
        ctx.actor.actor_id, db=db, cache=get_redis()
    )
    now = datetime.now(UTC)

    def _can_read(project_id) -> bool:
        for c in caps:
            if c.operation != "read" or c.resource_type != "project":
                continue
            if c.resource_id is not None and c.resource_id != project_id:
                continue
            if c.policy_blocked or (c.revoked_at is not None and c.revoked_at <= now):
                continue
            if c.expires_at is not None and c.expires_at <= now:
                continue
            return True
        return False

    return [
        ProjectListItem.model_validate(p)
        for p in projects
        if _can_read(p.id)
    ]


@router.get("/{project_slug}", response_model=ProjectRead)
async def get_project(pctx: ProjectContextDep, db: SessionDep) -> ProjectRead:
    ok = await can(
        pctx.actor.actor_id,
        Operation.READ,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        # Guests with a capability for a *different* project in this org
        # should still see a 404 here (not 403), so existence of the
        # specific project they don't have access to isn't disclosed.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project.not_found_or_forbidden"},
        )
    return ProjectRead.model_validate(pctx.project)


@router.patch("/{project_slug}", response_model=ProjectRead)
async def update_project(
    body: ProjectUpdateRequest,
    pctx: ProjectContextDep,
    db: SessionDep,
) -> ProjectRead:
    ok = await can(
        pctx.actor.actor_id,
        Operation.WRITE,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    try:
        project = await ProjectService.update(
            project_id=pctx.project.id,
            name=body.name,
            description=body.description,
        )
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project.not_found_or_forbidden"},
        ) from e
    return ProjectRead.model_validate(project)


@router.delete("/{project_slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(pctx: ProjectContextDep, db: SessionDep) -> Response:
    ok = await can(
        pctx.actor.actor_id,
        Operation.ADMIN,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    try:
        await ProjectService.soft_delete(
            project_id=pctx.project.id, actor_id=pctx.actor.actor_id
        )
    except ProjectNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project.not_found_or_forbidden"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Per-project guest share (UC-001) ─────────────────────────────────────


@router.post(
    "/{project_slug}/shares",
    status_code=status.HTTP_201_CREATED,
    response_model=ProjectShareResponse,
    dependencies=[Depends(require_verified_email)],
)
async def share_project(
    body: ProjectShareRequest,
    pctx: ProjectContextDep,
    db: SessionDep,
    background: BackgroundTasks,
) -> ProjectShareResponse:
    # `share:project` (held by owner/admin) is the right gate per ADR-013.
    ok = await can(
        pctx.actor.actor_id,
        Operation.SHARE,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    ttl = timedelta(days=body.ttl_days) if body.ttl_days is not None else None
    try:
        raw, share = await ProjectShareService.share(
            org_id=pctx.org.id,
            project_id=pctx.project.id,
            email=body.email,
            shared_by=pctx.actor.actor_id,
            ttl=ttl,
        )
    except ShareTTLError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "share.ttl_too_long", "message": str(e)},
        ) from e

    background.add_task(
        send_project_share,
        body.email,
        raw,
        org_name=pctx.org.name,
        project_name=pctx.project.name,
        inviter_email=pctx.actor.email,
        ttl_days=(share.expires_at - share.created_at).days or 1,
    )
    return ProjectShareResponse(
        id=share.id,
        project_id=share.project_id,
        email=share.email,
        expires_at=share.expires_at,
    )


@router.get(
    "/{project_slug}/shares",
    response_model=list[ProjectShareItem],
)
async def list_project_shares(
    pctx: ProjectContextDep, db: SessionDep
) -> list[ProjectShareItem]:
    # Listing pending shares is admin-flavoured visibility — gate on share.
    ok = await can(
        pctx.actor.actor_id,
        Operation.SHARE,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    rows = await ProjectShareService.list_pending_for_project(
        organisation_id=pctx.org.id, project_id=pctx.project.id
    )
    return [ProjectShareItem.model_validate(r) for r in rows]


@router.delete(
    "/{project_slug}/shares/{share_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_project_share(
    share_id: str,
    pctx: ProjectContextDep,
    db: SessionDep,
) -> Response:
    from uuid import UUID as _UUID

    try:
        sid = _UUID(share_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "share.not_found_or_expired"},
        ) from e

    ok = await can(
        pctx.actor.actor_id,
        Operation.SHARE,
        ResourceType.PROJECT,
        pctx.project.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "authz.forbidden"},
        )

    try:
        await ProjectShareService.revoke(
            share_id=sid, revoked_by=pctx.actor.actor_id
        )
    except ShareNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "share.not_found_or_expired"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Note: this route lives at the parent /orgs path, NOT under /orgs/{slug}/...
# because the accepting actor doesn't yet know which org the share belongs to.
# We declare it on a parallel router so it doesn't pick up the project_router
# prefix.
accept_share_router = APIRouter(prefix="/orgs", tags=["projects"])


@accept_share_router.post(
    "/projects/accept-share",
    status_code=status.HTTP_200_OK,
    response_model=AcceptShareResponse,
    dependencies=[Depends(require_verified_email)],
)
async def accept_project_share(
    body: AcceptShareRequest,
    actor: Annotated[CurrentActor, Depends(current_actor)],
) -> AcceptShareResponse:
    try:
        org, project = await ProjectShareService.accept(
            raw_token=body.token, accepting_actor_id=actor.actor_id
        )
    except ShareNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "share.not_found_or_expired"},
        ) from e
    return AcceptShareResponse(org_slug=org.slug, project_slug=project.slug)
