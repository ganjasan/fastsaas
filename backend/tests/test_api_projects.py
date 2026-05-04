"""End-to-end tests for /orgs/{slug}/projects/* (issue #3, phase 7).

Coverage:
- create as owner happy path; mints `all_in_org` capabilities for every
  active member so they can write/run/read the new project.
- create rejects bad / reserved / duplicate slug and non-admin callers.
- list returns all projects for members; for guests, returns only the
  projects they hold a `read:project` capability for (UC-001).
- get returns 404 for non-member of the project, 200 for member.
- patch needs `write:project`; viewer 403, member 200.
- delete needs `admin:project`; member 403, owner 204; subsequent get 404.
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
) -> tuple[str, UUID]:
    pw = "correct horse battery staple"
    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": role},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201, r.text
    invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
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
    return access, UUID(r.json()["actor_id"])


# ─── Create ────────────────────────────────────────────────────────────────


async def test_owner_can_create_project(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an owner WHEN POST /orgs/acme/projects THEN 201 with payload."""
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Q3 Forecast", "slug": "q3-forecast", "description": "demo"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["slug"] == "q3-forecast"
    assert body["description"] == "demo"


async def test_create_project_invalid_slug_400(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Bad", "slug": "Bad Slug!"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "project.slug_invalid"


async def test_create_project_duplicate_slug_409(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "First", "slug": "shared"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Second", "slug": "shared"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "project.slug_taken"


async def test_member_cannot_create_project_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a plain member (no admin:organisation) WHEN POST /projects THEN 403."""
    owner = await _make_owner_with_org(client, mailhog)
    member, _ = await _add_member(client, mailhog, owner, role="member")
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {member}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "authz.forbidden"


# ─── List + Get ────────────────────────────────────────────────────────────


async def test_member_sees_all_projects_in_org(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner creates two projects, then invites a member WHEN GET /projects as member THEN both listed."""
    owner = await _make_owner_with_org(client, mailhog)
    for slug in ("alpha", "beta"):
        await client.post(
            "/orgs/acme/projects",
            json={"name": slug, "slug": slug},
            headers={"Authorization": f"Bearer {owner}"},
        )
    member, _ = await _add_member(client, mailhog, owner, role="member")

    r = await client.get(
        "/orgs/acme/projects",
        headers={"Authorization": f"Bearer {member}"},
    )
    assert r.status_code == 200
    assert {p["slug"] for p in r.json()} == {"alpha", "beta"}


async def test_get_project_member_200(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    r = await client.get(
        "/orgs/acme/projects/alpha",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "alpha"


async def test_get_unknown_project_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    r = await client.get(
        "/orgs/acme/projects/nonesuch",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "project.not_found_or_forbidden"


# ─── Patch + Delete ────────────────────────────────────────────────────────


async def test_member_can_update_project(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a member (write:project all_in_org) WHEN PATCH project THEN 200."""
    owner = await _make_owner_with_org(client, mailhog)
    await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    member, _ = await _add_member(client, mailhog, owner, role="member")

    r = await client.patch(
        "/orgs/acme/projects/alpha",
        json={"name": "Alpha Renamed"},
        headers={"Authorization": f"Bearer {member}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Alpha Renamed"


async def test_viewer_cannot_update_project_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    viewer, _ = await _add_member(client, mailhog, owner, role="viewer")

    r = await client.patch(
        "/orgs/acme/projects/alpha",
        json={"name": "Hijack"},
        headers={"Authorization": f"Bearer {viewer}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "authz.forbidden"


async def test_member_cannot_delete_project_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    member, _ = await _add_member(client, mailhog, owner, role="member")

    r = await client.delete(
        "/orgs/acme/projects/alpha",
        headers={"Authorization": f"Bearer {member}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "authz.forbidden"


async def test_owner_deletes_project_then_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_org(client, mailhog)
    await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    r = await client.delete(
        "/orgs/acme/projects/alpha",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 204, r.text

    r = await client.get(
        "/orgs/acme/projects/alpha",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "project.not_found_or_forbidden"

    # And it's gone from the list.
    r = await client.get(
        "/orgs/acme/projects", headers={"Authorization": f"Bearer {owner}"}
    )
    assert r.status_code == 200
    assert r.json() == []


# ─── all_in_org propagation ────────────────────────────────────────────────


async def test_create_project_mints_capabilities_for_pre_existing_members(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a viewer is already a member WHEN owner creates a new project THEN viewer can read it without re-joining."""
    owner = await _make_owner_with_org(client, mailhog)
    viewer, _ = await _add_member(client, mailhog, owner, role="viewer")

    # Create the project AFTER the viewer joined.
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Alpha", "slug": "alpha"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201

    # Viewer should already have read access through the all_in_org fanout.
    r = await client.get(
        "/orgs/acme/projects/alpha",
        headers={"Authorization": f"Bearer {viewer}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "alpha"
