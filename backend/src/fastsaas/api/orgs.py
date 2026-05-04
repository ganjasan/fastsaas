"""Org-level endpoints: create / list / read / soft-delete + members.

`POST /orgs`, `GET /orgs`, and `POST /orgs/members/accept` are pre-tenant
(the caller picks which org to operate inside; the accept call only knows
the invitation token). The rest go through `tenant_context`, which sets
`app.current_org` and resolves membership.

Authorisation:
- POST   /                                  → any verified HUMAN may create an org (becomes owner).
- GET    /                                  → caller's own orgs only.
- GET    /{slug}                            → tenant_context (404 if not member/guest).
- DELETE /{slug}                            → can(admin, organisation, org.id).
- GET    /{slug}/members                    → require_org_member + can(read, organisation).
- POST   /{slug}/members/invite             → can(share, organisation, org.id).
- POST   /members/accept                    → only requires current_actor.
- PATCH  /{slug}/members/{actor_id}         → can(admin, organisation, org.id).
- DELETE /{slug}/members/{actor_id}         → can(admin, organisation, org.id).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import Response

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.cache.redis import get_redis
from fastsaas.identity.email import send_org_invitation
from fastsaas.identity.middleware import (
    SessionDep,
    current_actor,
    require_verified_email,
)
from fastsaas.identity.schemas import CurrentActor
from fastsaas.tenants.dependencies import TenantContext, TenantContextDep, require_org_member
from fastsaas.tenants.schemas import (
    AcceptInviteRequest,
    AcceptInviteResponse,
    InviteRequest,
    InviteResponse,
    MemberItem,
    MembersListResponse,
    OrgCreateRequest,
    OrgListItem,
    OrgRead,
    PendingInviteItem,
    RoleChangeRequest,
)
from fastsaas.tenants.service import (
    InviteAlreadyMemberError,
    InviteNotFoundError,
    InviteRoleError,
    LastOwnerError,
    MemberNotFoundError,
    MembershipService,
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


# ─── Members ────────────────────────────────────────────────────────────────


async def _require_org_admin(ctx: TenantContextDep, db: SessionDep) -> None:
    """Common gate for member-mutating routes — admin:organisation on the
    pinned org id. Raised as 403 authz.forbidden on miss."""
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


@router.get("/{slug}/members", response_model=MembersListResponse)
async def list_members(
    ctx: Annotated[TenantContext, Depends(require_org_member)],
    db: SessionDep,
) -> MembersListResponse:
    # Plain members get to see who they share an org with; admins
    # additionally see pending invitations. Anyone reading must hold
    # at least `read:organisation`.
    ok = await can(
        ctx.actor.actor_id,
        Operation.READ,
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

    rows = await MembershipService.list_members(ctx.org.id)
    members = [
        MemberItem(
            actor_id=m.actor_id,
            email=email,
            display_name=name,
            role=str(m.role),
            created_at=m.created_at,
        )
        for (m, email, name) in rows
    ]

    can_admin = await can(
        ctx.actor.actor_id,
        Operation.ADMIN,
        ResourceType.ORGANISATION,
        ctx.org.id,
        db=db,
        cache=get_redis(),
    )
    pending: list[PendingInviteItem] = []
    if can_admin:
        for inv in await MembershipService.list_pending_invites(ctx.org.id):
            pending.append(
                PendingInviteItem(
                    id=inv.id,
                    email=inv.email,
                    role=inv.role,
                    invited_by=inv.invited_by,
                    expires_at=inv.expires_at,
                    created_at=inv.created_at,
                )
            )

    return MembersListResponse(members=members, pending=pending)


@router.post(
    "/{slug}/members/invite",
    status_code=status.HTTP_201_CREATED,
    response_model=InviteResponse,
    dependencies=[Depends(require_verified_email)],
)
async def invite_member(
    body: InviteRequest,
    ctx: TenantContextDep,
    db: SessionDep,
    background: BackgroundTasks,
) -> InviteResponse:
    await _require_org_admin(ctx, db)

    try:
        raw, inv = await MembershipService.invite(
            org_id=ctx.org.id,
            email=body.email,
            role=body.role,
            invited_by=ctx.actor.actor_id,
        )
    except InviteRoleError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invite.role_invalid", "message": str(e)},
        ) from e
    except InviteAlreadyMemberError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "invite.already_member"},
        ) from e

    background.add_task(
        send_org_invitation,
        body.email,
        raw,
        org_name=ctx.org.name,
        inviter_email=ctx.actor.email,
    )
    return InviteResponse(
        id=inv.id, email=inv.email, role=inv.role, expires_at=inv.expires_at
    )


@router.post(
    "/members/accept",
    status_code=status.HTTP_200_OK,
    response_model=AcceptInviteResponse,
    dependencies=[Depends(require_verified_email)],
)
async def accept_invite(
    body: AcceptInviteRequest,
    actor: Annotated[CurrentActor, Depends(current_actor)],
) -> AcceptInviteResponse:
    try:
        org, role = await MembershipService.accept(
            raw_token=body.token, accepting_actor_id=actor.actor_id
        )
    except InviteNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "invite.not_found_or_expired"},
        ) from e
    return AcceptInviteResponse(org_slug=org.slug, role=role.value)


@router.patch("/{slug}/members/{actor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def change_member_role(
    actor_id: UUID,
    body: RoleChangeRequest,
    ctx: TenantContextDep,
    db: SessionDep,
) -> Response:
    await _require_org_admin(ctx, db)
    try:
        await MembershipService.change_role(
            org_id=ctx.org.id,
            target_actor_id=actor_id,
            new_role=body.role,
            actor_id=ctx.actor.actor_id,
        )
    except MemberNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "member.not_found"},
        ) from e
    except LastOwnerError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "org.last_owner"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{slug}/members/{actor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    actor_id: UUID,
    ctx: TenantContextDep,
    db: SessionDep,
) -> Response:
    await _require_org_admin(ctx, db)
    try:
        await MembershipService.remove(
            org_id=ctx.org.id,
            target_actor_id=actor_id,
            actor_id=ctx.actor.actor_id,
        )
    except MemberNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "member.not_found"},
        ) from e
    except LastOwnerError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "org.last_owner"},
        ) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
