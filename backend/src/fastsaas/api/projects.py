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

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.authz.check import _load_active_capabilities
from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import SessionDep, require_verified_email
from fastsaas.tenants.dependencies import (
    ProjectContextDep,
    TenantContextDep,
)
from fastsaas.tenants.schemas import (
    ProjectCreateRequest,
    ProjectListItem,
    ProjectRead,
    ProjectUpdateRequest,
)
from fastsaas.tenants.service import (
    ProjectNotFoundError,
    ProjectService,
    ProjectSlugTakenError,
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
