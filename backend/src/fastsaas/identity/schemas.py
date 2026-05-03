"""Pydantic request/response schemas for the identity API surface.

Kept separate from `models.py` (SQLModel ORM) so the wire shape can evolve
without altering the storage shape. `CurrentActor` is the typed view returned
by the `current_actor` dependency.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from fastsaas.identity.models import ActorType


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class MagicLinkRequestBody(BaseModel):
    email: EmailStr


class MagicLinkConsumeBody(BaseModel):
    token: str = Field(min_length=1)


class PasswordResetRequestBody(BaseModel):
    email: EmailStr


class PasswordResetConsumeBody(BaseModel):
    token: str = Field(min_length=1)
    password: str = Field(min_length=1)


class VerifyEmailBody(BaseModel):
    token: str = Field(min_length=1)


class TokensResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 900


class RegisterResponse(BaseModel):
    actor_id: UUID
    email: EmailStr
    email_verified: bool


class CurrentActor(BaseModel):
    actor_id: UUID
    actor_type: ActorType
    parent_actor_id: UUID | None
    email: EmailStr
    email_verified: bool
