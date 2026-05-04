"""Pydantic request/response schemas for the tenants API surface.

Kept separate from `models.py` (SQLModel ORM) so the wire shape can evolve
without altering the storage shape — same convention as identity/schemas.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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
