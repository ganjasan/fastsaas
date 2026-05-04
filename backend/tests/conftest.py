"""Test fixtures.

Per ADR-005: every test is async (`asyncio_mode = "auto"`).
Per ADR-007: a `tenant_session` fixture sets `SET LOCAL app.current_org` so RLS
policies enforce as they would in production.

Tests connect as `app_user` (no BYPASSRLS) — that is the actual app role and
is the only way to verify RLS-driven isolation actually works. Migrations are
expected to have been applied by `alembic_migrator` separately (`make migrate`).

Redis tests use database 15 (FLUSHDB on entry) so they don't collide with the
running dev environment on database 0.
"""

from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis, from_url
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas import cache as cache_module
from fastsaas.config import get_settings
from fastsaas.identity.auth import refresh as refresh_module
from fastsaas.main import app

_TEST_REDIS_DB = 15


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Per-test engine — pytest-asyncio creates a fresh event loop per test, and a
    session-scoped engine would hold connections bound to a closed loop."""
    settings = get_settings()
    eng = create_async_engine(settings.database_url, future=True)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """An app_user session inside a transaction — rolled back at teardown."""
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as s:
        async with s.begin():
            yield s
            await s.rollback()


@pytest.fixture
async def tenant_session(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Same as `session` but pre-sets `app.current_org` so RLS policies pass."""
    org_id = uuid4()
    await session.execute(text(f"SET LOCAL app.current_org = '{org_id}'"))
    yield session


@pytest.fixture
async def mailhog() -> AsyncIterator[AsyncClient]:
    """HTTP client to Mailhog (skips test if unreachable). Wipes mailbox on entry + exit."""
    base = get_settings().mailhog_http_url
    try:
        async with AsyncClient(timeout=1.5) as probe:
            r = await probe.get(f"{base}/api/v2/messages")
            if r.status_code != 200:
                pytest.skip("Mailhog returned non-200")
    except Exception:
        pytest.skip(f"Mailhog is not reachable at {base}")
    async with AsyncClient(base_url=base, timeout=5) as c:
        await c.delete("/api/v1/messages")
        yield c
        await c.delete("/api/v1/messages")


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI client — no real network.

    Disposes the fastsaas.db production engine before AND after the test:
    pytest-asyncio gives each test its own loop, but the module-level engine
    in `fastsaas.db` persists. Without a reset, the second test in a file
    talks to a connection pool bound to the previous (closed) loop.
    """
    from fastsaas import db

    await db.close_engine()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    await db.close_engine()


# FK dependency order — children first, then parents. `audit_log.actor_id`
# FKs `actors(id)` without cascade per ADR-006 / ADR-010 (immortal log), so
# audit rows must be wiped before `actors`. The other tables follow the
# tenant FK chain: shares → invitations → caps → projects → members → orgs.
_WIPE_ORDER: tuple[str, ...] = (
    "audit_log",
    "project_shares",
    "org_invitations",
    "capabilities",
    "projects",
    "organisation_members",
    "organisations",
    "actors",
)


async def _wipe_tables(tables: tuple[str, ...]) -> None:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s, s.begin():
            for tbl in tables:
                await s.execute(text(f"DELETE FROM {tbl}"))
    finally:
        await eng.dispose()


@pytest.fixture
async def clean_identity() -> AsyncIterator[None]:
    """Wipe `audit_log` + `actors` (cascading children) around each test.

    Integration tests hit real endpoints that commit to the live DB; without
    a wipe the next test sees yesterday's rows. Lighter than `wipe_state` —
    use this for auth-only tests that never touch tenancy.
    """
    light = ("audit_log", "actors")
    await _wipe_tables(light)
    yield
    await _wipe_tables(light)


@pytest.fixture
async def wipe_state() -> AsyncIterator[None]:
    """Wipe every tenant + identity + audit table around each test.

    Use this for tests that exercise routes touching orgs / members /
    projects / shares / capabilities. The dependency order in `_WIPE_ORDER`
    is the single source of truth — adding a new FK-bearing table is one
    edit here, not seven across the suite.
    """
    await _wipe_tables(_WIPE_ORDER)
    yield
    await _wipe_tables(_WIPE_ORDER)


@pytest.fixture
async def redis_client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Redis]:
    """Per-test Redis client on database 15 with FLUSHDB on entry.

    Re-points the module-level `cache.get_redis` cache so any production code
    under test (e.g. identity.auth.refresh) talks to the same isolated DB.
    """
    settings = get_settings()
    base = settings.redis_url.rsplit("/", 1)[0]
    test_url = f"{base}/{_TEST_REDIS_DB}"

    monkeypatch.setattr(settings, "redis_url", test_url)
    # Drop any cached client so production code reconnects under the new URL.
    monkeypatch.setattr(cache_module, "_client", None, raising=False)
    monkeypatch.setattr(cache_module.redis, "_client", None, raising=False)
    refresh_module.reload_scripts()

    client = from_url(test_url, encoding="utf-8", decode_responses=True)
    await client.flushdb()
    try:
        yield client
    finally:
        await client.flushdb()
        await client.aclose()
        # Force production cache to re-create on next test.
        monkeypatch.setattr(cache_module.redis, "_client", None, raising=False)
        refresh_module.reload_scripts()
