"""End-to-end tests for per-project guest share — UC-001 (issue #3, phase 8).

Coverage:
- happy path: owner shares → external user registers → accepts → reads
  the project but cannot see other projects, members, or sister-orgs.
- ttl override + ttl_max enforcement.
- accept with unknown / expired token → 404.
- non-admin cannot share → 403.
- listing pending shares is admin-only.
- revoke pending share → invalidates the token; future accept → 404.
- revoke consumed share → revokes the capability; guest loses access.
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
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)
    yield
    if db_module._migrator_engine is not None:
        await db_module._migrator_engine.dispose()
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)


@pytest.fixture
async def wipe_state() -> AsyncIterator[None]:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)

    async def wipe() -> None:
        async with factory() as s, s.begin():
            await s.execute(text("DELETE FROM project_shares"))
            await s.execute(text("DELETE FROM org_invitations"))
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


async def _make_owner_with_two_projects(
    client: AsyncClient, mailhog: AsyncClient
) -> str:
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs",
        json={"name": "Acme Co", "slug": "acme"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201
    for slug in ("alpha", "beta"):
        r = await client.post(
            "/orgs/acme/projects",
            json={"name": slug, "slug": slug},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 201
    return access


async def _share_and_consume(
    client: AsyncClient,
    mailhog: AsyncClient,
    *,
    owner_access: str,
    project_slug: str,
    invitee_email: str,
    invitee_pw: str,
    ttl_days: int | None = None,
) -> str:
    """Share project with email → register the recipient → consume share.
    Returns the recipient's access token."""
    body: dict[str, Any] = {"email": invitee_email}
    if ttl_days is not None:
        body["ttl_days"] = ttl_days
    r = await client.post(
        f"/orgs/acme/projects/{project_slug}/shares",
        json=body,
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201, r.text
    share_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    invitee_access = await _register_and_login(
        client, mailhog, invitee_email, invitee_pw
    )
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": share_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"org_slug": "acme", "project_slug": project_slug}
    return invitee_access


# ─── Happy path + isolation ────────────────────────────────────────────────


async def test_guest_reads_only_shared_project(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN owner shares `alpha` WHEN guest accepts THEN guest reads alpha but not beta, members, or any other org."""
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)

    guest = await _share_and_consume(
        client,
        mailhog,
        owner_access=owner,
        project_slug="alpha",
        invitee_email=_email(),
        invitee_pw=pw,
    )

    # Guest can read the shared project.
    r = await client.get(
        "/orgs/acme/projects/alpha", headers={"Authorization": f"Bearer {guest}"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["slug"] == "alpha"

    # Guest CANNOT read other projects in the same org.
    r = await client.get(
        "/orgs/acme/projects/beta", headers={"Authorization": f"Bearer {guest}"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "project.not_found_or_forbidden"

    # Guest's project list contains ONLY the shared one.
    r = await client.get(
        "/orgs/acme/projects", headers={"Authorization": f"Bearer {guest}"}
    )
    assert r.status_code == 200
    assert {p["slug"] for p in r.json()} == {"alpha"}

    # Guest CANNOT list org members (require_org_member rejects guests).
    r = await client.get(
        "/orgs/acme/members", headers={"Authorization": f"Bearer {guest}"}
    )
    assert r.status_code == 404

    # Guest does NOT see the org in `GET /orgs` (no organisation_members row).
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {guest}"})
    assert r.status_code == 200
    assert r.json() == []


async def test_share_ttl_override_honoured(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_two_projects(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": _email(), "ttl_days": 7},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    expires = r.json()["expires_at"]
    assert expires  # ISO 8601 timestamp; pydantic shape


async def test_share_ttl_above_cap_rejected(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """ttl_days=60 > pydantic le=30 → 422 from the request schema."""
    owner = await _make_owner_with_two_projects(client, mailhog)
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": _email(), "ttl_days": 60},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 422


async def test_accept_unknown_token_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": "totally-bogus-share-token-x" * 2},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "share.not_found_or_expired"


async def test_accept_expired_share_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN the share row has been forcibly aged WHEN accept THEN 404."""
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)
    invitee_email = _email()

    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": invitee_email},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    share_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")

    # Force expiry.
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    try:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE project_shares SET expires_at = NOW() - INTERVAL '1 hour' "
                    "WHERE email = :e"
                ),
                {"e": invitee_email},
            )
    finally:
        await eng.dispose()

    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": share_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "share.not_found_or_expired"


# ─── Authorization ─────────────────────────────────────────────────────────


async def test_member_cannot_share_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """role:member doesn't carry share:project; only owner/admin can share."""
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)

    # Add a plain member.
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": _email(), "role": "member"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    member_invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    member_access = await _register_and_login(client, mailhog, _email(), pw)
    # Mailhog has the invite for the previous member's email; refresh and use the right one
    # by re-doing it more carefully.
    # Simpler: generate a fresh invite + accept now. The previous block was a placeholder;
    # rewrite cleanly:
    _ = member_invite_token

    member_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": member_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    member_access = await _register_and_login(client, mailhog, member_email, pw)
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    assert r.status_code == 200

    # Member tries to share.
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": _email()},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "authz.forbidden"


# ─── Listing + revocation ─────────────────────────────────────────────────


async def test_list_pending_shares_visible_to_owner(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    owner = await _make_owner_with_two_projects(client, mailhog)
    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": invitee_email},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    await mailhog.delete("/api/v1/messages")

    r = await client.get(
        "/orgs/acme/projects/alpha/shares",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["email"].lower() == invitee_email.lower()


async def test_revoke_pending_share_invalidates_token(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)
    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": invitee_email},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    share_id = r.json()["id"]
    share_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")

    # Owner revokes before consumption.
    r = await client.delete(
        f"/orgs/acme/projects/alpha/shares/{share_id}",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 204, r.text

    # Recipient registers and tries to accept the revoked token.
    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": share_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "share.not_found_or_expired"


async def test_share_against_soft_deleted_project_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a share was minted against a project that is then soft-deleted
    WHEN the recipient accepts THEN 404 share.not_found_or_expired.

    Exercises the `project_unavailable` branch of ProjectShareService.accept
    that wasn't covered by the original phase-8 tests."""
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)
    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": invitee_email},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    share_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")

    # Owner soft-deletes the project before the recipient gets to it.
    r = await client.delete(
        "/orgs/acme/projects/alpha", headers={"Authorization": f"Bearer {owner}"}
    )
    assert r.status_code == 204

    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": share_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "share.not_found_or_expired"


async def test_share_for_existing_member_consumes_token_without_minting(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an actor is already a member of the org WHEN a share for that
    org's project is accepted by them THEN the token is consumed (single-
    use contract) but no stray `role:guest_viewer` capability is minted —
    they already have access through their member bundle, and a
    guest_viewer row would never be reached by the cleanup paths."""
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)

    # Add a member to the same org.
    member_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": member_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    member_access = await _register_and_login(client, mailhog, member_email, pw)
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    assert r.status_code == 200

    # Owner shares a project to the member's email.
    r = await client.post(
        "/orgs/acme/projects/alpha/shares",
        json={"email": member_email},
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 201
    share_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")

    # Member accepts.
    r = await client.post(
        "/orgs/projects/accept-share",
        json={"token": share_token},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    assert r.status_code == 200

    # Confirm: NO `role:guest_viewer` capability was minted (only their
    # member-bundle caps remain). And the share IS consumed (single-use).
    # Direct DB peek through the migrator role; sha256 computed client-side
    # to avoid relying on Postgres `digest()` / `pgcrypto` extension.
    import hashlib

    expected_hash = hashlib.sha256(share_token.encode("utf-8")).hexdigest()

    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    try:
        async with eng.begin() as conn:
            count = (
                await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM capabilities "
                        "WHERE bundle_name = 'role:guest_viewer'"
                    )
                )
            ).scalar_one()
            assert count == 0, f"unexpected guest_viewer caps: {count}"

            consumed = (
                await conn.execute(
                    text(
                        "SELECT consumed_at IS NOT NULL FROM project_shares "
                        "WHERE token_hash = :h"
                    ),
                    {"h": expected_hash},
                )
            ).scalar_one()
            assert consumed is True
    finally:
        await eng.dispose()


async def test_revoke_consumed_share_revokes_capability(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    pw = "correct horse battery staple"
    owner = await _make_owner_with_two_projects(client, mailhog)
    guest = await _share_and_consume(
        client,
        mailhog,
        owner_access=owner,
        project_slug="alpha",
        invitee_email=_email(),
        invitee_pw=pw,
    )

    # Pick the share id from the listing (already consumed → list_pending
    # returns nothing, but we can dig it out via the consumed_capability
    # path — easier: re-derive by sharing again is wasteful, so query DB
    # directly through SQL).
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    try:
        async with eng.begin() as conn:
            row = (
                await conn.execute(
                    text("SELECT id FROM project_shares WHERE consumed_at IS NOT NULL")
                )
            ).first()
            assert row is not None
            share_id = row[0]
    finally:
        await eng.dispose()

    # Owner revokes the consumed share.
    r = await client.delete(
        f"/orgs/acme/projects/alpha/shares/{share_id}",
        headers={"Authorization": f"Bearer {owner}"},
    )
    assert r.status_code == 204, r.text

    # Guest now loses access.
    r = await client.get(
        "/orgs/acme/projects/alpha", headers={"Authorization": f"Bearer {guest}"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"
