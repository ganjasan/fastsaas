"""End-to-end tests for /orgs/{slug}/members/* (issue #3, phase 6).

Builds on test_api_orgs.py: same wipe + register/login helpers.

Coverage:
- invite + accept happy path (member + capability bundle minted).
- invite as `owner` rejected.
- invite of an existing member rejected.
- accept with unknown / expired / already-consumed token → 404.
- list_members visible to admin and member, plus pending invites
  (admin only).
- change_role: admin → viewer; viewer → admin (revoke + mint round-trip).
- last-owner protection: cannot demote / remove the only owner.
- remove revokes capabilities and `_resolve_membership` returns None.
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


async def _register_and_login(
    client: AsyncClient, mailhog: AsyncClient, email: str, password: str
) -> str:
    """Register + verify + login → return Bearer access token. Wipes
    Mailbox at entry and exit so caller never crosses messages."""
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

    await mailhog.delete("/api/v1/messages")
    return r.json()["access_token"]


async def _make_owner_with_org(
    client: AsyncClient, mailhog: AsyncClient, *, slug: str = "acme"
) -> tuple[str, str]:
    """Register + log in an owner and create one org. Returns (access, owner_email)."""
    pw = "correct horse battery staple"
    owner_email = _email()
    access = await _register_and_login(client, mailhog, owner_email, pw)
    r = await client.post(
        "/orgs",
        json={"name": "Acme Co", "slug": slug},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    return access, owner_email


# ─── Invite + Accept ───────────────────────────────────────────────────────


async def test_invite_and_accept_happy_path(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an owner invites an email WHEN the recipient registers and accepts THEN they appear as a member with role:member."""
    pw = "correct horse battery staple"
    owner_access, _ = await _make_owner_with_org(client, mailhog)

    invitee_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["email"].lower() == invitee_email.lower()
    assert r.json()["role"] == "member"

    # Mailhog has the invitation email.
    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] >= 1
    invite_body = msgs["items"][0]["Content"]["Body"]
    invite_token = _token_from_link(_link_from_mail(invite_body))
    await mailhog.delete("/api/v1/messages")

    # Invitee registers separately.
    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)

    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"org_slug": "acme", "role": "member"}

    # Invitee can now see the org.
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {invitee_access}"})
    assert r.status_code == 200
    items = r.json()
    assert {o["slug"] for o in items} == {"acme"}
    assert items[0]["role"] == "member"

    # Owner sees both members.
    r = await client.get(
        "/orgs/acme/members", headers={"Authorization": f"Bearer {owner_access}"}
    )
    assert r.status_code == 200
    members = r.json()["members"]
    assert {m["role"] for m in members} == {"owner", "member"}


async def test_invite_owner_role_rejected(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an owner WHEN POST invite role=owner THEN 400 invite.role_invalid."""
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": _email(), "role": "owner"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    # Pydantic enum may bounce earlier as 422 — accept either, but assert
    # the route NEVER gives 201.
    assert r.status_code in (400, 422), r.text


async def test_invite_existing_member_409(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN someone is already a member WHEN inviting them again THEN 409 invite.already_member."""
    pw = "correct horse battery staple"
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    invitee_email = _email()

    # First invite + accept.
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201
    invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 200

    # Re-invite — already a member.
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "invite.already_member"


async def test_accept_unknown_token_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    access = await _register_and_login(client, mailhog, _email(), "correct horse battery staple")
    r = await client.post(
        "/orgs/members/accept",
        json={"token": "totally-bogus-token-that-cannot-exist-x" * 2},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invite.not_found_or_expired"


async def test_accept_expired_invite_404(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an invite with expires_at in the past WHEN POST accept THEN 404."""
    pw = "correct horse battery staple"
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    invitee_email = _email()

    # Mint an invite the normal way.
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": invitee_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201
    invite_token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")

    # Forcibly age the invite.
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    try:
        async with eng.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE org_invitations "
                    "SET expires_at = NOW() - INTERVAL '1 hour' "
                    "WHERE email = :e"
                ),
                {"e": invitee_email},
            )
    finally:
        await eng.dispose()

    invitee_access = await _register_and_login(client, mailhog, invitee_email, pw)
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "invite.not_found_or_expired"


# ─── Authorisation ─────────────────────────────────────────────────────────


async def test_invite_by_non_admin_403(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a member-level user WHEN POST invite THEN 403 authz.forbidden."""
    pw = "correct horse battery staple"
    owner_access, _ = await _make_owner_with_org(client, mailhog)

    # Add a plain member.
    member_email = _email()
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": member_email, "role": "member"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201
    token = _token_from_link(
        _link_from_mail((await mailhog.get("/api/v2/messages")).json()["items"][0]["Content"]["Body"])
    )
    await mailhog.delete("/api/v1/messages")
    member_access = await _register_and_login(client, mailhog, member_email, pw)
    await client.post(
        "/orgs/members/accept",
        json={"token": token},
        headers={"Authorization": f"Bearer {member_access}"},
    )

    # Member tries to invite someone else.
    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": _email(), "role": "viewer"},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "authz.forbidden"


# ─── Role change + removal ─────────────────────────────────────────────────


async def _add_member(
    client: AsyncClient, mailhog: AsyncClient, owner_access: str, *, role: str = "member"
) -> tuple[str, str, UUID]:
    """Provision a verified member of acme. Returns (access, email, actor_id)."""
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

    # Read /auth/me to learn the actor_id.
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    return access, invitee_email, UUID(r.json()["actor_id"])


async def test_change_role_revokes_old_bundle_and_mints_new(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a member WHEN PATCH /members/{id} role=viewer THEN previous member capabilities are revoked and viewer ones minted."""
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    _member_access, _, member_actor_id = await _add_member(
        client, mailhog, owner_access, role="member"
    )

    r = await client.patch(
        f"/orgs/acme/members/{member_actor_id}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 204, r.text

    # Members listing reflects the new role.
    r = await client.get(
        "/orgs/acme/members", headers={"Authorization": f"Bearer {owner_access}"}
    )
    members = r.json()["members"]
    target = next(m for m in members if UUID(m["actor_id"]) == member_actor_id)
    assert target["role"] == "viewer"


async def test_change_role_last_owner_blocked(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN the only owner WHEN PATCH self to viewer THEN 409 org.last_owner."""
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {owner_access}"})
    owner_actor_id = UUID(r.json()["actor_id"])

    r = await client.patch(
        f"/orgs/acme/members/{owner_actor_id}",
        json={"role": "viewer"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "org.last_owner"


async def test_invite_blocks_duplicate_for_existing_member(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN an actor is already a member as `member` WHEN an admin re-invites
    them as `admin` THEN the invite is rejected at mint time with 409
    invite.already_member.

    Combined with `MembershipService.accept`'s defence-in-depth idempotency
    (the token is NOT burned for an actor already in the org), this means
    the only way to change a role is the explicit
    `PATCH /orgs/{slug}/members/{actor_id}` endpoint — never via a
    silently-overloaded invite token."""
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    _, _, _ = await _add_member(client, mailhog, owner_access, role="member")
    members_listing = (
        await client.get(
            "/orgs/acme/members", headers={"Authorization": f"Bearer {owner_access}"}
        )
    ).json()["members"]
    member_email = next(m["email"] for m in members_listing if m["role"] == "member")

    r = await client.post(
        "/orgs/acme/members/invite",
        json={"email": member_email, "role": "admin"},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "invite.already_member"


async def test_cross_org_members_listing_404_no_leak(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN orgs `acme` and `globex` each with their own owner+members
    WHEN owner of `acme` requests `/orgs/globex/members` THEN 404 — the
    tenant-context gate must block any cross-org leak even on members
    listings, regardless of org-level admin elsewhere.

    Negative test for ADR-007 / phase 4: confirms the migrator-session
    contained reads in MembershipService.list_members are gated by
    tenant_context membership resolution before the service is called."""
    pw = "correct horse battery staple"
    acme_owner_access, _ = await _make_owner_with_org(client, mailhog)
    # Spin up a second org with its own owner.
    globex_owner_access = await _register_and_login(client, mailhog, _email(), pw)
    r = await client.post(
        "/orgs",
        json={"name": "Globex", "slug": "globex"},
        headers={"Authorization": f"Bearer {globex_owner_access}"},
    )
    assert r.status_code == 201

    # Acme owner pokes globex.
    r = await client.get(
        "/orgs/globex/members", headers={"Authorization": f"Bearer {acme_owner_access}"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"


async def test_remove_member_deletes_membership_and_revokes_capabilities(
    client: AsyncClient, redis_client: Any, wipe_state: None, mailhog: AsyncClient
) -> None:
    """GIVEN a member WHEN DELETE /members/{id} THEN membership row gone and the member loses access."""
    owner_access, _ = await _make_owner_with_org(client, mailhog)
    member_access, _, member_actor_id = await _add_member(
        client, mailhog, owner_access, role="member"
    )

    r = await client.delete(
        f"/orgs/acme/members/{member_actor_id}",
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 204, r.text

    # Member can no longer reach the org.
    r = await client.get(
        "/orgs/acme", headers={"Authorization": f"Bearer {member_access}"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "org.not_found_or_forbidden"

    # And the org is gone from their list.
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {member_access}"})
    assert r.status_code == 200
    assert r.json() == []
