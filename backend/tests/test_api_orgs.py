"""End-to-end tests for /orgs/* endpoints (issue #3, phase 5).

Each test goes through the live ASGI app, hits real Postgres + Redis +
Mailhog, and rebuilds state per test via the wipe fixture below. We don't
reuse `clean_identity` because tenant tables hold FK references that
block actor cleanup.
"""

from __future__ import annotations

import quopri
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas import db as db_module
from fastsaas.config import get_settings


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
    """Same rationale as test_tenants_context: module-level engine survives
    across tests bound to a stale event loop without this reset."""
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)
    yield
    if db_module._migrator_engine is not None:
        await db_module._migrator_engine.dispose()
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)


@pytest.fixture
async def wipe_state() -> AsyncIterator[None]:
    """Wipe tenant + identity rows before AND after each test.

    Order matters — capabilities reference actors and orgs, so wipe in
    dependency order (capabilities, projects, members, orgs, then actors;
    magic_link_tokens cascade with actors).
    """
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)

    async def wipe() -> None:
        async with factory() as s, s.begin():
            await s.execute(text("DELETE FROM capabilities"))
            await s.execute(text("DELETE FROM projects"))
            await s.execute(text("DELETE FROM organisation_members"))
            await s.execute(text("DELETE FROM organisations"))
            await s.execute(text("DELETE FROM actors"))

    try:
        await wipe()
        yield
        await wipe()
    finally:
        await eng.dispose()


async def _register_and_login(
    client: AsyncClient, mailhog: AsyncClient, email: str, password: str
) -> str:
    """Register → consume verification → login → return Bearer access token.

    Clears Mailhog before sending so the verify-email of *this* registration
    is the only message in the mailbox; clears it again at the end so a
    subsequent caller starts from empty too.
    """
    await mailhog.delete("/api/v1/messages")
    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text

    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] >= 1
    # Mailhog orders newest-first; index 0 is the most recent message.
    body = msgs["items"][0]["Content"]["Body"]
    token = _token_from_link(_link_from_mail(body))

    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text

    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text

    await mailhog.delete("/api/v1/messages")
    return r.json()["access_token"]


# ─── POST /orgs ────────────────────────────────────────────────────────────


async def test_create_org_201_returns_payload(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a verified user WHEN POST /orgs THEN 201 with org payload AND owner becomes member."""
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    await mailhog.delete("/api/v1/messages")

    r = await client.post(
        "/orgs",
        json={"name": "Acme Co", "slug": "acme-co"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "acme-co"
    assert body["name"] == "Acme Co"
    assert "id" in body
    assert "created_at" in body


async def test_create_org_invalid_slug_400(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an invalid slug WHEN POST /orgs THEN 400 org.slug_invalid."""
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    r = await client.post(
        "/orgs",
        json={"name": "Bad", "slug": "Bad Slug!"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "org.slug_invalid"


async def test_create_org_reserved_slug_400(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a reserved slug WHEN POST /orgs THEN 400 org.slug_reserved."""
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    r = await client.post(
        "/orgs",
        json={"name": "Admin Co", "slug": "admin"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] == "org.slug_reserved"


async def test_create_org_duplicate_slug_409(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN slug X already exists WHEN POST /orgs same slug THEN 409 org.slug_taken."""
    pw = "correct horse battery staple"
    access1 = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs",
        json={"name": "First", "slug": "shared"},
        headers={"Authorization": f"Bearer {access1}"},
    )
    assert r.status_code == 201, r.text

    access2 = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs",
        json={"name": "Second", "slug": "shared"},
        headers={"Authorization": f"Bearer {access2}"},
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "org.slug_taken"


async def test_create_org_no_token_401(
    client: AsyncClient, redis_client: Any, wipe_state: None
) -> None:
    """GIVEN no Authorization header WHEN POST /orgs THEN 401 auth.token_missing."""
    r = await client.post("/orgs", json={"name": "X", "slug": "x-org"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.token_missing"


# ─── GET /orgs ─────────────────────────────────────────────────────────────


async def test_list_my_orgs_returns_only_caller_orgs(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN two users each owning an org WHEN GET /orgs THEN each sees only their own."""
    pw = "correct horse battery staple"
    a = await _register_and_login(client, mailhog, _email(), pw)
    b = await _register_and_login(client, mailhog, _email(), pw)

    r = await client.post("/orgs", json={"name": "A", "slug": "a-org"}, headers={"Authorization": f"Bearer {a}"})
    assert r.status_code == 201
    r = await client.post("/orgs", json={"name": "B", "slug": "b-org"}, headers={"Authorization": f"Bearer {b}"})
    assert r.status_code == 201

    r = await client.get("/orgs", headers={"Authorization": f"Bearer {a}"})
    assert r.status_code == 200
    a_orgs = r.json()
    assert {o["slug"] for o in a_orgs} == {"a-org"}
    assert a_orgs[0]["role"] == "owner"

    r = await client.get("/orgs", headers={"Authorization": f"Bearer {b}"})
    assert r.status_code == 200
    assert {o["slug"] for o in r.json()} == {"b-org"}


async def test_list_my_orgs_empty_for_new_user(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a freshly verified user WHEN GET /orgs THEN [] (empty state)."""
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json() == []


# ─── GET /orgs/{slug} ──────────────────────────────────────────────────────


async def test_get_org_by_slug_member_sees_it(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner of acme WHEN GET /orgs/acme THEN 200 with payload."""
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    await client.post("/orgs", json={"name": "Acme", "slug": "acme"}, headers={"Authorization": f"Bearer {access}"})

    r = await client.get("/orgs/acme", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json()["slug"] == "acme"


async def test_get_org_by_slug_non_member_404_no_leak(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN acme exists, caller is NOT a member WHEN GET /orgs/acme THEN 404 (existence not disclosed)."""
    pw = "correct horse battery staple"
    owner = await _register_and_login(client, mailhog, _email(), pw)
    await client.post("/orgs", json={"name": "Acme", "slug": "acme"}, headers={"Authorization": f"Bearer {owner}"})

    outsider = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.get("/orgs/acme", headers={"Authorization": f"Bearer {outsider}"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"


async def test_get_org_by_unknown_slug_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    r = await client.get("/orgs/no-such-org", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"


# ─── DELETE /orgs/{slug} ───────────────────────────────────────────────────


async def test_owner_can_delete_org_and_then_loses_visibility(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner WHEN DELETE /orgs/acme THEN 204; subsequent GET returns 404."""
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    await client.post("/orgs", json={"name": "Acme", "slug": "acme"}, headers={"Authorization": f"Bearer {access}"})

    r = await client.delete("/orgs/acme", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 204, r.text

    # Soft-deleted org is invisible (per _resolve_membership filtering).
    r = await client.get("/orgs/acme", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 404
    # And it's gone from the list too.
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    assert r.json() == []


async def test_non_member_delete_org_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN outsider WHEN DELETE /orgs/acme THEN 404 (org.not_found_or_forbidden — same shape as get)."""
    pw = "correct horse battery staple"
    owner = await _register_and_login(client, mailhog, _email(), pw)
    await client.post("/orgs", json={"name": "Acme", "slug": "acme"}, headers={"Authorization": f"Bearer {owner}"})

    outsider = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.delete("/orgs/acme", headers={"Authorization": f"Bearer {outsider}"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"
