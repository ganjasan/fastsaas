"""Platform admin endpoints — staff-only surfaces.

Today this ships only `/admin/me` so the frontend AdminShell can gate on
the response. Subsequent epics (#20-#23) plug their endpoints here under
the same `require_platform_staff` dep.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import text

from fastsaas.admin.dependencies import PlatformStaffDep
from fastsaas.admin.schemas import AdminMeResponse
from fastsaas.identity.middleware import SessionDep

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/me", response_model=AdminMeResponse)
async def admin_me(actor: PlatformStaffDep, db: SessionDep) -> AdminMeResponse:
    """Return the staff actor's identity. Non-staff get 403 from the dep."""
    result = await db.execute(
        text("SELECT display_name FROM actors WHERE id = :id"),
        {"id": str(actor.actor_id)},
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "actor.not_found"},
        )
    return AdminMeResponse(
        actor_id=actor.actor_id,
        email=actor.email,
        display_name=str(row[0]),
        is_platform_staff=True,
    )
