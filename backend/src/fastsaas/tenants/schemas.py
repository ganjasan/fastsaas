"""Pydantic request/response schemas for the tenants API surface.

Kept separate from `models.py` (SQLModel ORM) so the wire shape can evolve
without altering the storage shape — same convention as identity/schemas.py.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fastsaas.tenants.models import OrganisationRole


class ThemePreset(StrEnum):
    """Phase 1 preset enum per ADR-012. Phase 2 will add a free-form theme
    editor; until then the wire contract is one of these five values."""

    DEFAULT = "default"
    MODERN = "modern"
    CORPORATE = "corporate"
    DARK = "dark"
    HIGH_CONTRAST = "high-contrast"


class ThemeModeDefault(StrEnum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class OrgThemeUpdateRequest(BaseModel):
    """Body for `PATCH /orgs/{slug}/theme`. Replaces (not merges) the
    persisted `organisations.theme` JSONB."""

    model_config = ConfigDict(extra="forbid")

    preset: ThemePreset
    mode_default: ThemeModeDefault | None = None


class OrgCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=63)


class OrgRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    theme: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class OrgListItem(BaseModel):
    """Lightweight projection used by `GET /orgs`. Carries the caller's role
    so the org switcher can render badges without a second round-trip."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    role: str  # OrganisationRole, kept as str for orval / serialisation simplicity
    created_at: datetime


# ── Membership ──────────────────────────────────────────────────────────────


class InviteRequest(BaseModel):
    email: EmailStr
    role: OrganisationRole = Field(
        default=OrganisationRole.MEMBER,
        description="Destination role for the invitee. `owner` is rejected.",
    )


class InviteResponse(BaseModel):
    """Returned by POST /orgs/{slug}/members/invite. Doesn't expose the raw
    token — that goes only in the email."""

    id: UUID
    email: str
    role: str
    expires_at: datetime


class AcceptInviteRequest(BaseModel):
    token: str = Field(min_length=20)


class AcceptInviteResponse(BaseModel):
    org_slug: str
    role: str


class MemberItem(BaseModel):
    """Row of GET /orgs/{slug}/members. Email may be `None` for non-HUMAN
    actors (none ship in v1; future-proofing)."""

    actor_id: UUID
    email: str | None
    display_name: str
    role: str
    created_at: datetime


class PendingInviteItem(BaseModel):
    id: UUID
    email: str
    role: str
    invited_by: UUID
    expires_at: datetime
    created_at: datetime


class MembersListResponse(BaseModel):
    members: list[MemberItem]
    pending: list[PendingInviteItem]


class RoleChangeRequest(BaseModel):
    role: OrganisationRole


# ── Projects ────────────────────────────────────────────────────────────────


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=3, max_length=63)
    description: str | None = Field(default=None, max_length=1000)


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    created_by: UUID
    created_at: datetime


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    created_at: datetime


# ── Project share (UC-001) ──────────────────────────────────────────────────


class ProjectShareRequest(BaseModel):
    email: EmailStr
    ttl_days: int | None = Field(
        default=None,
        ge=1,
        le=30,
        description="TTL override; default 14, capped at 30.",
    )


class ProjectShareResponse(BaseModel):
    id: UUID
    project_id: UUID
    email: str
    expires_at: datetime


class ProjectShareItem(BaseModel):
    """Lighter projection for `GET /projects/{slug}/shares` listings."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    shared_by: UUID
    expires_at: datetime
    created_at: datetime


class AcceptShareRequest(BaseModel):
    token: str = Field(min_length=20)


class AcceptShareResponse(BaseModel):
    org_slug: str
    project_slug: str
