"""SQLModel mirror of the `capabilities` table (per ADR-013, migration 0001 + 0004).

Authorization checks SHALL go through `authz.can(...)`, never direct queries
against this table from route handlers. Provisioning goes through
`authz.service.mint_bundle` / `mint_capability` which set `metadata.org_id` so
RLS `org_admin_scope` policy can match.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class Capability(SQLModel, table=True):
    __tablename__ = "capabilities"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    actor_id: UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False)
    )
    operation: str = Field(sa_column=Column(String, nullable=False))
    resource_type: str = Field(sa_column=Column(String, nullable=False))
    resource_id: UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    conditions: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
    bundle_name: str | None = Field(default=None, sa_column=Column(String, nullable=True))
    granted_by: UUID | None = Field(
        default=None,
        sa_column=Column(PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=True),
    )
    granted_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
    expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    revoked_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    policy_blocked: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default=text("FALSE")),
    )
    # SQLModel can't use `metadata` (Table.metadata clash); column is named
    # `metadata` in the DB but exposed as `meta` on the ORM model.
    meta: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(
            "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
        ),
    )
