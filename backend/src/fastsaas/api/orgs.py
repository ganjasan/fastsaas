"""Org-level endpoints: create / list / read / soft-delete.

`POST /orgs` and `GET /orgs` are pre-tenant (the caller picks which org to
operate inside); they take only `current_actor`. `GET /orgs/{slug}` and
`DELETE /orgs/{slug}` go through `tenant_context`, which sets
`app.current_org` and resolves membership.

Authorisation:
- POST  → any verified HUMAN may create an org (becomes owner).
- GET / — list — only orgs the actor is a member of (service-side filter).
- GET   /{slug} — gated by tenant_context (404 if not member/guest).
- DELETE /{slug} — capability check `admin:organisation` against the
  pinned org id.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import (
    SessionDep,
    current_actor,
    require_verified_email,
)
from fastsaas.identity.schemas import CurrentActor
from fastsaas.tenants.dependencies import TenantContextDep
from fastsaas.tenants.schemas import OrgCreateRequest, OrgListItem, OrgRead
from fastsaas.tenants.service import (
    OrganisationService,
    OrgNotFoundError,
    OrgSlugTakenError,
)
from fastsaas.tenants.slugs import SlugError, validate_slug

router = APIRouter(prefix="/orgs", tags=["orgs"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=OrgRead,
    dependencies=[Depends(require_verified_email)],
)
async def create_org(
    body: OrgCreateRequest,
    actor: Annotated[CurrentActor, Depends(current_actor)],
) -> OrgRead:
    try:
        validate_slug(body.slug, kind="org")
    except SlugError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.code, "message": str(e)},
        ) from e

    try:
        org = await OrganisationService.create(
            name=body.name, slug=body.slug, owner_actor_id=actor.actor_id
        )
    except OrgSlugTakenError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "org.slug_taken", "message": "slug already in use"},
        ) from e
    return OrgRead.model_validate(org)


@router.get("", response_model=list[OrgListItem])
async def list_my_orgs(
    actor: Annotated[CurrentActor, Depends(current_actor)],
) -> list[OrgListItem]:
    pairs = await OrganisationService.list_for_actor(actor.actor_id)
    return [
        OrgListItem(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role=role.value,
            created_at=org.created_at,
        )
        for (org, role) in pairs
    ]


@router.get("/{slug}", response_model=OrgRead)
async def get_org(ctx: TenantContextDep) -> OrgRead:
    return OrgRead.model_validate(ctx.org)


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_org(ctx: TenantContextDep, db: SessionDep) -> Response:
    # Guests cannot delete (they have no admin capability anyway, but we
    # short-circuit for clarity).
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
        await OrganisationService.soft_delete(org_id=ctx.org.id, actor_id=ctx.actor.actor_id)
    except OrgNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "org.not_found_or_forbidden"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
