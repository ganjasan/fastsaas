"""SQLModel ORM mirrors of the migration-0001 actor schema and migration-0003 magic_link_tokens.

CTI per ADR-009: `Actor` is the parent; `User`, `OAuthIdentity`, and (later)
`Agent`/`Service` are children. v1 reads/writes only `User` (HUMAN actors).

`Actor.id` is generated app-side as UUID v7 per ADR-006; the DB also has a
`gen_random_uuid()` default as a fallback for direct SQL inserts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ActorType(StrEnum):
    HUMAN = "HUMAN"
    AGENT = "AGENT"
    SERVICE = "SERVICE"


class MagicLinkPurpose(StrEnum):
    EMAIL_VERIFICATION = "email_verification"
    MAGIC_LINK_LOGIN = "magic_link_login"
    PASSWORD_RESET = "password_reset"
    ORG_INVITATION = "org_invitation"


class Actor(SQLModel, table=True):
    __tablename__ = "actors"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    actor_type: ActorType = Field(sa_column=Column(String, nullable=False))
    parent_actor_id: UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True),
    )
    display_name: str = Field(sa_column=Column(String, nullable=False))
    # Platform-staff flag (per ADR-019): structural cross-org authority,
    # toggled out-of-band via `make seed-platform-staff`. The `can()`
    # short-circuit reads this column for `(PLATFORM_ADMIN, PLATFORM)`
    # checks; org-level capabilities are unaffected.
    is_platform_staff: bool = Field(
        default=False,
        sa_column=Column(
            "is_platform_staff",
            nullable=False,
            server_default=text("FALSE"),
        ),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class User(SQLModel, table=True):
    __tablename__ = "users"

    actor_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("actors.id", ondelete="CASCADE"),
            primary_key=True,
        )
    )
    email: str = Field(sa_column=Column(CITEXT, unique=True, nullable=False))
    password_hash: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    email_verified: bool = Field(
        default=False, sa_column=Column("email_verified", nullable=False, server_default=text("FALSE"))
    )
    locale: str = Field(
        default="en", sa_column=Column(String, nullable=False, server_default=text("'en'"))
    )
    timezone: str = Field(
        default="UTC", sa_column=Column(String, nullable=False, server_default=text("'UTC'"))
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )


class OAuthIdentity(SQLModel, table=True):
    __tablename__ = "oauth_identities"

    provider: str = Field(sa_column=Column(String, primary_key=True))
    provider_uid: str = Field(sa_column=Column(String, primary_key=True))
    user_actor_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("users.actor_id", ondelete="CASCADE"),
            nullable=False,
        )
    )


class MagicLinkToken(SQLModel, table=True):
    __tablename__ = "magic_link_tokens"
    __table_args__ = (
        Index(
            "magic_link_tokens_actor_purpose_idx",
            "actor_id",
            "purpose",
            postgresql_where=text("consumed_at IS NULL"),
        ),
    )

    token_hash: str = Field(sa_column=Column(String, primary_key=True))
    purpose: MagicLinkPurpose = Field(sa_column=Column(String, nullable=False))
    actor_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("actors.id", ondelete="CASCADE"),
            nullable=False,
        )
    )
    email: str = Field(sa_column=Column(CITEXT, nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    consumed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
