"""SQLModel ORM mirrors of the multi-tenant tables.

`Organisation` and `Project` ship with `slug CITEXT UNIQUE` per
`migration 0004_orgs_slugs_and_member_rls`. `OrganisationMember.role` is the
denormalised display name of the actor's primary capability bundle in this org
(see authz/bundles.py); enforcement always goes through `can(...)`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class OrganisationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"
    COMPLIANCE_OFFICER = "compliance_officer"


class Organisation(SQLModel, table=True):
    __tablename__ = "organisations"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    slug: str = Field(sa_column=Column(CITEXT, unique=True, nullable=False))
    theme: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    quota: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class OrganisationMember(SQLModel, table=True):
    __tablename__ = "organisation_members"

    organisation_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("organisations.id"),
            primary_key=True,
        )
    )
    actor_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            ForeignKey("actors.id"),
            primary_key=True,
        )
    )
    role: OrganisationRole = Field(sa_column=Column(String, nullable=False))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )


class OrgInvitation(SQLModel, table=True):
    __tablename__ = "org_invitations"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    organisation_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
        )
    )
    email: str = Field(sa_column=Column(CITEXT, nullable=False))
    role: str = Field(sa_column=Column(String, nullable=False))
    token_hash: str = Field(sa_column=Column(String, unique=True, nullable=False))
    invited_by: UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    consumed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    consumed_by: UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )


class ProjectShare(SQLModel, table=True):
    __tablename__ = "project_shares"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    project_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
        )
    )
    organisation_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
        )
    )
    email: str = Field(sa_column=Column(CITEXT, nullable=False))
    token_hash: str = Field(sa_column=Column(String, unique=True, nullable=False))
    shared_by: UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False)
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    consumed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    consumed_by: UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True),
    )
    consumed_capability_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("capabilities.id"), nullable=True
        ),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )


class Project(SQLModel, table=True):
    __tablename__ = "projects"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    organisation_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    slug: str = Field(sa_column=Column(CITEXT, nullable=False))
    description: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    created_by: UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False)
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
