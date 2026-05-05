"""Audit endpoints — currently `POST /orgs/{slug}/audit/scrub`.

The scrub endpoint is the GDPR Art.17 right-to-erasure path for
`audit_log.intent_metadata`. Authorisation flow:

1. Tenant context resolves the slug → pins `app.current_org` and binds
   the actor's membership / guest status (404 for non-members).
2. `can(actor, SCRUB, AUDIT_LOG, org.id)` gates the endpoint — strictly
   stricter than `READ`. Compliance officers (read only) cannot scrub.
3. The service swaps to the migrator session for the actual UPDATE
   (RLS forbids UPDATE on `audit_log` for `app_user` regardless of
   capability).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import ValidationError

from fastsaas.audit.scrub import (
    AuditScrubService,
    ScrubFilterError,
    ScrubRequest,
    ScrubResult,
)
from fastsaas.authz import Operation, ResourceType, can
from fastsaas.cache.redis import get_redis
from fastsaas.identity.middleware import SessionDep
from fastsaas.tenants.dependencies import TenantContextDep

router = APIRouter(prefix="/orgs", tags=["audit"])


@router.post("/{slug}/audit/scrub", response_model=ScrubResult)
async def scrub_audit_log(
    ctx: TenantContextDep,
    db: SessionDep,
    body: Annotated[dict[str, Any], Body(...)],
) -> ScrubResult:
    # Parse the request manually so unknown keys map to a stable 400 code
    # rather than FastAPI's default 422 — the destructive-endpoint contract
    # in design.md §D9 requires explicit error codes.
    try:
        request = ScrubRequest.model_validate(body)
    except ValidationError as e:
        if any(err["type"] == "extra_forbidden" for err in e.errors()):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "audit.scrub.unknown_filter_key",
                    "message": "request body contains unknown keys",
                },
            ) from e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "audit.scrub.invalid_filter",
                "message": str(e),
            },
        ) from e

    ok = await can(
        ctx.actor.actor_id,
        Operation.SCRUB,
        ResourceType.AUDIT_LOG,
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
        return await AuditScrubService.scrub(
            org_id=ctx.org.id,
            dpo=ctx.actor,
            scrub_filter=request.filter,
            dry_run=request.dry_run,
        )
    except ScrubFilterError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": e.code, "message": str(e)},
        ) from e
