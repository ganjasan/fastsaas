"""Pydantic response shapes for the admin API surface."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AdminMeResponse(BaseModel):
    """Returned by `GET /admin/me`. Used by the frontend to gate the
    AdminShell — non-staff actors get 403 from the dependency before this
    type is ever serialised, so `is_platform_staff` is always True here.
    """

    model_config = ConfigDict(from_attributes=True)

    actor_id: UUID
    email: str | None
    display_name: str
    is_platform_staff: bool
