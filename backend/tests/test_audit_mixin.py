"""Unit-ish tests for `AuditedModel` mapper listeners.

Defines a temporary `audit_test_widget` table at module load — its lifecycle
is per-test-stack rather than per-test, because SQLAlchemy mapper events
are wired at class creation time and re-creating the model would fight the
SQLAlchemy registry. Each test wipes the rows it inserted.

Covers:
- `after_insert` emits `action="create"` with full `after` snapshot.
- `after_update` emits `action="update"` with only changed columns.
- soft-delete flip (`deleted_at` NULL→ts) emits `action="delete"`.
- restore flip (`deleted_at` ts→NULL) emits `action="restore"`.
- `__audit_skip__ = True` opts out cleanly.
- `__audit_redact__` masks per-model sensitive fields.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import Field, SQLModel

from fastsaas.audit.context import set_audit_context
from fastsaas.audit.mixin import AuditedModel
from fastsaas.audit.redact import REDACTED_LITERAL
from fastsaas.config import get_settings
from fastsaas.identity.models import ActorType
from fastsaas.identity.schemas import CurrentActor


class _AuditTestWidget(AuditedModel, table=True):
    """Tiny audited test table for mixin behaviour.

    Defined here (not in src/) so it ships only with the test suite. The
    table is created at fixture setup via raw DDL — keeping it out of
    Alembic so production migrations stay clean.
    """

    __tablename__ = "audit_test_widget"
    __audit_entity_type__: ClassVar[str] = "widget"
    __audit_redact__: ClassVar[frozenset[str]] = frozenset({"raw_secret"})

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
    raw_secret: str = Field(sa_column=Column(String, nullable=False))
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class _AuditTestSkipped(AuditedModel, table=True):
    """Twin table with `__audit_skip__ = True` to verify opt-out."""

    __tablename__ = "audit_test_skipped"
    __audit_entity_type__: ClassVar[str] = "skipped_widget"
    __audit_skip__: ClassVar[bool] = True

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))


@pytest.fixture(scope="module", autouse=True)
async def _ensure_test_tables() -> AsyncIterator[None]:
    """Create the test-only tables once and drop after the module finishes.

    Uses `SQLModel.metadata.create_all` against the SQLAlchemy `__table__`
    descriptors so the column definitions on `_AuditTestWidget` /
    `_AuditTestSkipped` are the single source of truth — adding a column
    on the model picks up automatically.
    """
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    tables = [_AuditTestWidget.__table__, _AuditTestSkipped.__table__]
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.create_all(sync_conn, tables=tables)
        )
    yield
    async with eng.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: SQLModel.metadata.drop_all(sync_conn, tables=tables)
        )
    await eng.dispose()


@pytest.fixture
async def actor_id() -> AsyncIterator[UUID]:
    """Insert a HUMAN actor row that satisfies `audit_log.actor_id` FK and
    yield its id. The audit rows we create reference it; teardown wipes
    them along with the actor."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    aid = uuid4()
    try:
        async with factory() as s, s.begin():
            await s.execute(
                text(
                    "INSERT INTO actors (id, actor_type, display_name) "
                    "VALUES (:id, 'HUMAN', 'audit-mixin-test')"
                ),
                {"id": str(aid)},
            )
        yield aid
    finally:
        async with factory() as s, s.begin():
            await s.execute(text("DELETE FROM audit_log WHERE actor_id = :id"), {"id": str(aid)})
            await s.execute(text("DELETE FROM audit_test_widget"))
            await s.execute(text("DELETE FROM audit_test_skipped"))
            await s.execute(text("DELETE FROM actors WHERE id = :id"), {"id": str(aid)})
        await eng.dispose()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            yield s
    finally:
        await eng.dispose()


def _actor(actor_id: UUID) -> CurrentActor:
    return CurrentActor(
        actor_id=actor_id,
        actor_type=ActorType.HUMAN,
        parent_actor_id=None,
        email="audit-mixin-test@example.com",
        email_verified=True,
    )


async def _peek(db: AsyncSession, *, entity_id: UUID) -> list[Any]:
    rows = (
        await db.execute(
            text(
                "SELECT action, diff::text AS diff_text, intent_metadata::text AS md_text "
                "FROM audit_log WHERE entity_id = :eid ORDER BY timestamp ASC"
            ),
            {"eid": str(entity_id)},
        )
    ).all()
    return rows


# ─── Insert / update / delete listeners ────────────────────────────────────


async def test_after_insert_emits_create_with_full_after_snapshot(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN audit context pinned to a known actor
    with set_audit_context(_actor(actor_id)):
        async with db_session.begin():
            # WHEN inserting a widget
            w = _AuditTestWidget(name="alpha", raw_secret="hush")
            db_session.add(w)
            await db_session.flush()
            wid = w.id

    # THEN one create row exists for the widget
    rows = await _peek(db_session, entity_id=wid)
    assert len(rows) == 1
    assert rows[0].action == "create"
    # AND the redacted secret is masked while name is preserved
    assert "alpha" in rows[0].diff_text
    assert REDACTED_LITERAL in rows[0].diff_text
    assert "hush" not in rows[0].diff_text


async def test_after_update_emits_update_with_only_changed_columns(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN a widget in the DB
    with set_audit_context(_actor(actor_id)):
        async with db_session.begin():
            w = _AuditTestWidget(name="alpha", raw_secret="s1")
            db_session.add(w)
            await db_session.flush()
            wid = w.id

        # WHEN flipping only `name`
        async with db_session.begin():
            w2 = await db_session.get(_AuditTestWidget, wid)
            assert w2 is not None
            w2.name = "beta"
            db_session.add(w2)
            await db_session.flush()

    # THEN two audit rows exist (create + update); the update's diff covers
    # `name` only — `raw_secret` and `deleted_at` should not appear
    rows = await _peek(db_session, entity_id=wid)
    assert [r.action for r in rows] == ["create", "update"]
    assert "alpha" in rows[1].diff_text and "beta" in rows[1].diff_text
    # The update diff should not have raw_secret in either side
    assert '"raw_secret"' not in rows[1].diff_text


async def test_soft_delete_flip_is_recorded_as_action_delete(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN a widget in the DB
    with set_audit_context(_actor(actor_id)):
        async with db_session.begin():
            w = _AuditTestWidget(name="alpha", raw_secret="s1")
            db_session.add(w)
            await db_session.flush()
            wid = w.id

        # WHEN flipping `deleted_at` from NULL → timestamp
        async with db_session.begin():
            w2 = await db_session.get(_AuditTestWidget, wid)
            assert w2 is not None
            w2.deleted_at = datetime.now(UTC)
            db_session.add(w2)
            await db_session.flush()

    # THEN the second audit row's action is "delete", not "update"
    rows = await _peek(db_session, entity_id=wid)
    assert [r.action for r in rows] == ["create", "delete"]


async def test_restore_flip_is_recorded_as_action_restore(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN a widget that has been soft-deleted
    with set_audit_context(_actor(actor_id)):
        async with db_session.begin():
            w = _AuditTestWidget(
                name="alpha", raw_secret="s1", deleted_at=datetime.now(UTC)
            )
            db_session.add(w)
            await db_session.flush()
            wid = w.id

        # WHEN flipping `deleted_at` back to NULL
        async with db_session.begin():
            w2 = await db_session.get(_AuditTestWidget, wid)
            assert w2 is not None
            w2.deleted_at = None
            db_session.add(w2)
            await db_session.flush()

    # THEN the second audit row's action is "restore"
    rows = await _peek(db_session, entity_id=wid)
    assert [r.action for r in rows] == ["create", "restore"]


async def test_audit_skip_true_emits_no_audit_row(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN audit context pinned and a class with __audit_skip__ = True
    with set_audit_context(_actor(actor_id)):
        async with db_session.begin():
            # WHEN we insert a row of that class
            obj = _AuditTestSkipped(name="quiet")
            db_session.add(obj)
            await db_session.flush()
            oid = obj.id

    # THEN no audit row was written for it
    rows = await _peek(db_session, entity_id=oid)
    assert rows == []


async def test_no_audit_when_actor_var_is_unset(
    actor_id: UUID, db_session: AsyncSession
) -> None:
    # GIVEN audit context NOT pinned (simulating a worker / migration write
    # happening outside any HTTP request)
    async with db_session.begin():
        # WHEN we insert a widget directly
        w = _AuditTestWidget(name="orphan", raw_secret="s1")
        db_session.add(w)
        await db_session.flush()
        wid = w.id

    # THEN the mixin emits nothing — the explicit `record(...)` API is the
    # right tool for offline writes; silent skip avoids fabricating an actor
    rows = await _peek(db_session, entity_id=wid)
    assert rows == []
