"""Async DB engine + session factory.

Per ADR-005: asyncpg + SQLAlchemy 2.x async API.
Per ADR-007: each request opens a transaction and SETs `app.current_org` LOCAL.

Two engines coexist:
- `app_user` (no BYPASSRLS) — the request engine; subject to all RLS policies.
- `alembic_migrator` (BYPASSRLS) — used by alembic and by short bootstrap
  lookups that need to read tenant-scoped data before `app.current_org` is
  known (e.g. resolving org-by-slug + membership for the tenant_context
  dependency). NEVER used for user-driven mutations from route code.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_migrator_engine: AsyncEngine | None = None
_migrator_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Open a session inside a transaction; commit on success, rollback on error."""
    factory = get_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


def get_migrator_engine() -> AsyncEngine:
    """Lazy BYPASSRLS engine for short bootstrap reads (e.g. tenant-context)."""
    global _migrator_engine
    if _migrator_engine is None:
        settings = get_settings()
        _migrator_engine = create_async_engine(
            settings.database_url_migrator,
            pool_pre_ping=True,
            future=True,
            # Bootstrap reads are short and infrequent; a small pool is enough.
            pool_size=2,
            max_overflow=4,
        )
    return _migrator_engine


def get_migrator_session_factory() -> async_sessionmaker[AsyncSession]:
    global _migrator_session_factory
    if _migrator_session_factory is None:
        _migrator_session_factory = async_sessionmaker(
            bind=get_migrator_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _migrator_session_factory


@asynccontextmanager
async def migrator_session_scope() -> AsyncIterator[AsyncSession]:
    """Open a BYPASSRLS session inside a transaction.

    Use sparingly — application code should NOT mutate user data through this
    session, because it bypasses tenant isolation. Limited to: alembic, the
    tenant_context bootstrap lookup, and the clean_identity test fixture.
    """
    factory = get_migrator_session_factory()
    async with factory() as session:
        async with session.begin():
            yield session


async def close_engine() -> None:
    global _engine, _session_factory, _migrator_engine, _migrator_session_factory
    if _engine is not None:
        await _engine.dispose()
    if _migrator_engine is not None:
        await _migrator_engine.dispose()
    _engine = None
    _session_factory = None
    _migrator_engine = None
    _migrator_session_factory = None
