"""SQLModel mirror of `audit_log` (migration 0001).

ORM is for reads (compliance UI, tests, future admin surface). All writes
go through `audit.service.record(...)`. Per ADR-010 the table is immortal
and the schema is locked — this class only adds Python typing on top.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    timestamp: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    )
    actor_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("actors.id"), nullable=False
        )
    )
    actor_type: str = Field(sa_column=Column(String, nullable=False))
    parent_actor_id: UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    organisation_id: UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    intent_hash: str = Field(sa_column=Column(String, nullable=False))
    entity_type: str = Field(sa_column=Column(String, nullable=False))
    entity_id: UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    action: str = Field(sa_column=Column(String, nullable=False))
    diff: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSONB, nullable=False)
    )
    intent_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )
