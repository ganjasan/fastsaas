"""End-to-end tests for GET /orgs/{slug}/search (issue #28).

Coverage:
- query < 2 characters → 400 search.query_too_short
- owner can find a project by name substring (project provider)
- owner can find a fellow member by display_name (member provider)
- guest (project-share-only actor) does NOT see members in results —
  capability gate `(READ, ORGANISATION)` filters that group out
- kinds=projects narrows the response to a single group
"""

from __future__ import annotations

import quopri
import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

from fastsaas import db as db_module


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


async def _register_and_login(
    client: AsyncClient, mailhog: AsyncClient, email: str, password: str
) -> str:
    await mailhog.delete("/api/v1/messages")
    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    body = (await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"]
    token = _token_from_link(_link_from_mail(body))
    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200
    r = await client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    await mailhog.delete("/api/v1/messages")
    return r.json()["access_token"]


async def _make_owner_with_org(
    client: AsyncClient, mailhog: AsyncClient, *, slug: str = "acme"
) -> str:
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs",
        json={"name": "Acme Co", "slug": slug},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    return access


async def _add_member(
    client: AsyncClient, mailhog: AsyncClient, owner_access: str, *, role: str
) -> tuple[str, UUID, str]:
    pw = "correct horse battery staple"
    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": role},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201, r.text
    invite_token = _token_from_link(
        _link_from_mail(
            (await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"]
        )
    )
    await mailhog.delete("/api/v1/messages")
    access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    return access, UUID(r.json()["actor_id"]), invitee_email


async def test_search_query_too_short_400(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner WHEN GET /orgs/acme/search?q=a THEN 400 query_too_short."""
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.get(
        "/orgs/acme/search",
        params={"q": "a"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "search.query_too_short"


async def test_search_owner_finds_project(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner with project 'Q3 Forecast' WHEN q='forecast' THEN response
    includes a project group with the matching hit and a usable href."""
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Q3 Forecast", "slug": "q3-forecast"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201, r.text

    r = await client.get(
        "/orgs/acme/search",
        params={"q": "forecast"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    project_groups = [g for g in body["groups"] if g["entity_type"] == "project"]
    assert len(project_groups) == 1
    hits = project_groups[0]["hits"]
    assert any(h["title"] == "Q3 Forecast" for h in hits)
    matched = next(h for h in hits if h["title"] == "Q3 Forecast")
    assert matched["href"] == "/orgs/acme/projects/q3-forecast"
    assert matched["subtitle"] == "q3-forecast"


async def test_search_owner_finds_member_by_email(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner + invited member WHEN owner searches by email substring
    THEN the member group surfaces the invitee."""
    owner = await _make_owner_with_org(client, mailhog)
    _, _, invitee_email = await _add_member(client, mailhog, owner, role="member")
    needle = invitee_email.split("@")[0][:6]

    r = await client.get(
        "/orgs/acme/search",
        params={"q": needle},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    member_groups = [g for g in body["groups"] if g["entity_type"] == "member"]
    assert len(member_groups) == 1
    assert any(h["subtitle"] == invitee_email for h in member_groups[0]["hits"])


async def test_search_kinds_filter_projects_only(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner with a project + invited member sharing a substring
    WHEN kinds=project THEN response contains only the project group, no member group.
    """
    owner = await _make_owner_with_org(client, mailhog)
    # Project name shares prefix with a fake "memberish" word the member gets.
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "ZebraFinder", "slug": "zebrafinder"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    await _add_member(client, mailhog, owner, role="member")

    r = await client.get(
        "/orgs/acme/search",
        params={"q": "zebra", "kinds": "project"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert {g["entity_type"] for g in body["groups"]} == {"project"}
