"""Integration tests for the platform-admin foundation (issue #19).

Drives the live ASGI app + the seed CLI and asserts:
- `can(actor, PLATFORM_ADMIN, PLATFORM)` reflects `actors.is_platform_staff`.
- `GET /admin/me` returns 200 for staff, 403 for non-staff, 401 for unauthenticated.
- `seed_platform_staff` flips the flag and writes one audit row.
"""

from __future__ import annotations

import quopri
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas import db as db_module
from fastsaas.authz import Operation, ResourceType, can
from fastsaas.config import get_settings
from fastsaas.scripts.seed_platform_staff import _promote


def _email() -> str:
    return f"u-{uuid4().hex[:10]}@example.com"


def _link_from_mail(body: str) -> str:
    decoded = quopri.decodestring(body).decode("utf-8", errors="replace")
    m = re.search(r"https?://[^\s\"<>]+", decoded)
    assert m, f"no link in mail body: {decoded[:200]}"
    return m.group(0)


def _token_from_link(link: str) -> str:
    return link.rsplit("/", 1)[-1]


@pytest.fixture(autouse=True)
async def _reset_migrator_engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)
    yield
    if db_module._migrator_engine is not None:
        await db_module._migrator_engine.dispose()
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)


@pytest.fixture
async def migrator_session() -> AsyncIterator[AsyncSession]:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            yield s
    finally:
        await eng.dispose()


async def _register_and_login(
    client: AsyncClient, mailhog: AsyncClient, email: str, password: str
) -> tuple[str, UUID]:
    """Register → verify → login → return (access_token, actor_id)."""
    await mailhog.delete("/api/v1/messages")
    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text

    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] >= 1
    body = msgs["items"][0]["Content"]["Body"]
    token = _token_from_link(_link_from_mail(body))
    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    access = r.json()["access_token"]

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    actor_id = UUID(r.json()["actor_id"])

    await mailhog.delete("/api/v1/messages")
    return access, actor_id


# ─── /admin/me ─────────────────────────────────────────────────────────────


async def test_admin_me_unauthenticated_401(
    client: AsyncClient, redis_client: Any, wipe_state: None
) -> None:
    """GIVEN no Authorization header WHEN GET /admin/me THEN 401."""
    r = await client.get("/admin/me")
    assert r.status_code == 401


async def test_admin_me_non_staff_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an authenticated non-staff user WHEN GET /admin/me THEN 403 authz.forbidden."""
    pw = "correct horse battery staple"
    access, _ = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.get("/admin/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "authz.forbidden"


async def test_admin_me_staff_200(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a user with is_platform_staff=TRUE WHEN GET /admin/me THEN 200 with actor payload."""
    pw = "correct horse battery staple"
    email = _email()
    access, _ = await _register_and_login(client, mailhog, email, pw)
    # Promote via the seed CLI (the canonical path).
    rc = await _promote(email)
    assert rc == 0

    r = await client.get("/admin/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_platform_staff"] is True
    assert body["email"] == email


# ─── seed_platform_staff CLI ───────────────────────────────────────────────


async def test_seed_platform_staff_flips_flag_and_audits(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    """GIVEN an existing user WHEN seed_platform_staff runs THEN flag flips + one audit row appended."""
    pw = "correct horse battery staple"
    email = _email()
    _, actor_id = await _register_and_login(client, mailhog, email, pw)

    rc = await _promote(email)
    assert rc == 0

    # Flag flipped.
    flag = (
        await migrator_session.execute(
            text("SELECT is_platform_staff FROM actors WHERE id = :id"),
            {"id": str(actor_id)},
        )
    ).scalar_one()
    assert flag is True

    # One audit row with the right diff.
    rows = (
        await migrator_session.execute(
            text(
                "SELECT diff FROM audit_log "
                "WHERE entity_type = 'actor' AND entity_id = :id AND action = 'update'"
            ),
            {"id": str(actor_id)},
        )
    ).all()
    assert len(rows) == 1
    diff = rows[0][0]
    assert diff["before"]["is_platform_staff"] is False
    assert diff["after"]["is_platform_staff"] is True


async def test_seed_platform_staff_unknown_email_nonzero(
    client: AsyncClient, redis_client: Any, wipe_state: None
) -> None:
    """GIVEN an email with no user WHEN seed_platform_staff runs THEN exit code != 0."""
    rc = await _promote("nobody-here@example.com")
    assert rc != 0


async def test_seed_platform_staff_already_staff_is_noop(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    """GIVEN an already-staff user WHEN seed_platform_staff runs THEN exit 0 + no second audit row."""
    pw = "correct horse battery staple"
    email = _email()
    _, actor_id = await _register_and_login(client, mailhog, email, pw)
    assert await _promote(email) == 0
    # Re-run.
    assert await _promote(email) == 0

    rows = (
        await migrator_session.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE entity_type = 'actor' AND entity_id = :id"
            ),
            {"id": str(actor_id)},
        )
    ).scalar_one()
    assert rows == 1


# ─── can() short-circuit ────────────────────────────────────────────────────


async def test_can_platform_admin_reflects_flag(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
) -> None:
    """GIVEN a fresh actor WHEN can(PLATFORM_ADMIN, PLATFORM) is called THEN it returns the flag value."""
    pw = "correct horse battery staple"
    email = _email()
    _, actor_id = await _register_and_login(client, mailhog, email, pw)

    settings = get_settings()
    eng = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        # Pre-promotion: flag is FALSE → can() returns False.
        async with factory() as s:
            ok = await can(
                actor_id, Operation.PLATFORM_ADMIN, ResourceType.PLATFORM, db=s
            )
        assert ok is False

        # Promote.
        assert await _promote(email) == 0

        # Post-promotion: flag is TRUE → can() returns True.
        async with factory() as s:
            ok = await can(
                actor_id, Operation.PLATFORM_ADMIN, ResourceType.PLATFORM, db=s
            )
        assert ok is True
    finally:
        await eng.dispose()
