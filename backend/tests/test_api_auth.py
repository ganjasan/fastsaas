"""End-to-end tests for the /auth/* router.

Each test goes through the live ASGI app (no mocks of FastAPI internals) and
hits real Postgres, Redis (db 15), and — where flagged — Mailhog. Identity
tables are wiped per test via `clean_identity` so tests don't see each
other's actors.
"""

from __future__ import annotations

import quopri
import re
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from fastsaas.config import get_settings


def _email() -> str:
    """Test email under RFC 2606 example.com — pydantic's EmailStr rejects .local / .test."""
    return f"u-{uuid4().hex[:10]}@example.com"


def _link_from_mail(body: str) -> str:
    """Extract the first http(s) URL from a QP-encoded multipart body."""
    decoded = quopri.decodestring(body).decode("utf-8", errors="replace")
    m = re.search(r"https?://[^\s\"<>]+", decoded)
    assert m, f"no link in mail body: {decoded[:200]}"
    return m.group(0)


def _token_from_link(link: str) -> str:
    return link.rsplit("/", 1)[-1]


async def _register_and_verify(
    client: AsyncClient, mailhog: AsyncClient, email: str, password: str
) -> None:
    """Helper: register, fetch the verification mail, consume it."""
    r = await client.post(
        "/auth/register", json={"email": email, "password": password}
    )
    assert r.status_code == 201, r.text
    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] >= 1
    body = msgs["items"][0]["Content"]["Body"]
    token = _token_from_link(_link_from_mail(body))
    r = await client.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text


# ─── /auth/register ────────────────────────────────────────────────────────


async def test_register_creates_user_and_emails_verification(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a fresh email WHEN POST /auth/register THEN 201 and a verification email lands."""
    email = _email()
    r = await client.post(
        "/auth/register", json={"email": email, "password": "correct horse battery staple"}
    )
    assert r.status_code == 201
    payload = r.json()
    assert payload["email"] == email
    assert payload["email_verified"] is False

    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] == 1
    body = msgs["items"][0]["Content"]["Body"]
    base = get_settings().app_url.rstrip("/")
    assert f"{base}/auth/verify-email/" in body


async def test_register_short_password_rejected(
    client: AsyncClient, redis_client: Any, clean_identity: None
) -> None:
    """GIVEN a password under policy WHEN POST /auth/register THEN 400 auth.password_too_short."""
    r = await client.post("/auth/register", json={"email": _email(), "password": "short"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "auth.password_too_short"


async def test_register_duplicate_email_409(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN an email already in users WHEN re-registered THEN 409 auth.email_taken."""
    email = _email()
    pw = "correct horse battery staple"
    r1 = await client.post("/auth/register", json={"email": email, "password": pw})
    assert r1.status_code == 201
    r2 = await client.post("/auth/register", json={"email": email, "password": pw})
    assert r2.status_code == 409
    assert r2.json()["detail"]["code"] == "auth.email_taken"


# ─── /auth/login ───────────────────────────────────────────────────────────


async def test_login_unverified_email_403(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN registered-but-unverified user WHEN logging in THEN 403 auth.email_unverified."""
    email = _email()
    pw = "correct horse battery staple"
    await client.post("/auth/register", json={"email": email, "password": pw})
    r = await client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "auth.email_unverified"


async def test_login_wrong_password_401_generic(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN verified user + wrong password WHEN logging in THEN 401 auth.invalid_credentials."""
    email = _email()
    await _register_and_verify(client, mailhog, email, "correct horse battery staple")
    r = await client.post("/auth/login", json={"email": email, "password": "wrong-pw-xxx-xxx"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.invalid_credentials"


async def test_login_unknown_email_returns_same_401(
    client: AsyncClient, redis_client: Any, clean_identity: None
) -> None:
    """GIVEN no such user WHEN logging in THEN same 401 as wrong-password (no enumeration)."""
    r = await client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "anything-12-chars-ok"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.invalid_credentials"


async def test_login_success_returns_tokens_and_cookie(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a verified user WHEN logging in THEN 200 + access body + refresh cookie attrs."""
    email = _email()
    pw = "correct horse battery staple"
    await _register_and_verify(client, mailhog, email, pw)
    r = await client.post("/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 900
    assert body["access_token"]

    set_cookie = r.headers.get_list("set-cookie")
    refresh_cookies = [c for c in set_cookie if c.startswith("refresh_token=")]
    assert refresh_cookies
    raw = refresh_cookies[0]
    assert "HttpOnly" in raw
    assert "SameSite=lax" in raw or "SameSite=Lax" in raw
    assert "Path=/auth" in raw
    assert "Max-Age=2592000" in raw


# ─── /auth/me ──────────────────────────────────────────────────────────────


async def test_me_with_valid_bearer_returns_actor(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN an authenticated bearer WHEN GET /auth/me THEN actor + email_verified=true."""
    email = _email()
    pw = "correct horse battery staple"
    await _register_and_verify(client, mailhog, email, pw)
    login = await client.post("/auth/login", json={"email": email, "password": pw})
    access = login.json()["access_token"]

    r = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200
    me = r.json()
    assert me["email"] == email
    assert me["email_verified"] is True
    assert me["actor_type"] == "HUMAN"
    assert me["parent_actor_id"] is None


async def test_me_without_token_401(client: AsyncClient) -> None:
    """GIVEN no auth header WHEN GET /auth/me THEN 401 auth.token_missing."""
    r = await client.get("/auth/me")
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.token_missing"


async def test_me_with_garbage_token_401_invalid(client: AsyncClient) -> None:
    """GIVEN gibberish bearer token WHEN GET /auth/me THEN 401 auth.token_invalid."""
    r = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "auth.token_invalid"


# ─── /auth/refresh + /auth/logout ──────────────────────────────────────────


async def test_refresh_without_x_refresh_header_400(client: AsyncClient) -> None:
    """GIVEN no X-Refresh:1 WHEN POST /auth/refresh THEN 400 auth.refresh_missing_header."""
    r = await client.post("/auth/refresh")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "auth.refresh_missing_header"


async def test_refresh_rotates_token(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a fresh login WHEN POST /auth/refresh THEN cookie's jti rotates."""
    email = _email()
    pw = "correct horse battery staple"
    await _register_and_verify(client, mailhog, email, pw)
    login = await client.post("/auth/login", json={"email": email, "password": pw})
    first_refresh = login.cookies.get("refresh_token")

    r = await client.post("/auth/refresh", headers={"X-Refresh": "1"})
    assert r.status_code == 200
    assert r.json()["access_token"]  # access body present
    second_refresh = r.cookies.get("refresh_token")
    assert second_refresh
    # Refresh tokens carry distinct jti claims, so the encoded JWTs differ even at 1-second resolution.
    assert first_refresh != second_refresh


async def test_refresh_reuse_blacklists_family(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a rotated family WHEN replaying the old cookie THEN 401 auth.refresh_reused."""
    email = _email()
    pw = "correct horse battery staple"
    await _register_and_verify(client, mailhog, email, pw)
    login = await client.post("/auth/login", json={"email": email, "password": pw})
    old_cookie = login.headers["set-cookie"]
    old_refresh = old_cookie.split("refresh_token=")[1].split(";")[0]

    # First refresh succeeds (uses the cookie httpx persisted).
    r1 = await client.post("/auth/refresh", headers={"X-Refresh": "1"})
    assert r1.status_code == 200

    # Replay the OLD cookie — overwrite the jar's current cookie with the old value.
    r2 = await client.post(
        "/auth/refresh",
        headers={"X-Refresh": "1", "Cookie": f"refresh_token={old_refresh}"},
    )
    assert r2.status_code == 401
    assert r2.json()["detail"]["code"] == "auth.refresh_reused"


async def test_logout_clears_cookie_and_revokes(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a logged-in session WHEN POST /auth/logout THEN cookie is cleared and refresh fails."""
    email = _email()
    pw = "correct horse battery staple"
    await _register_and_verify(client, mailhog, email, pw)
    await client.post("/auth/login", json={"email": email, "password": pw})

    r = await client.post("/auth/logout")
    assert r.status_code == 204
    assert any(
        "refresh_token=" in c and "Max-Age=0" in c
        for c in r.headers.get_list("set-cookie")
    )

    # Refresh after logout: cookie was cleared, so we should hit 401 token_missing.
    r2 = await client.post("/auth/refresh", headers={"X-Refresh": "1"})
    assert r2.status_code == 401


# ─── magic-link / password-reset ───────────────────────────────────────────


async def test_magic_link_full_flow(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a verified user WHEN requesting + consuming a magic-link THEN tokens are issued."""
    email = _email()
    await _register_and_verify(client, mailhog, email, "correct horse battery staple")
    await mailhog.delete("/api/v1/messages")  # fresh slate for the magic-link email

    req = await client.post("/auth/magic-link/request", json={"email": email})
    assert req.status_code == 202
    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] == 1
    token = _token_from_link(_link_from_mail(msgs["items"][0]["Content"]["Body"]))

    consume = await client.post("/auth/magic-link/consume", json={"token": token})
    assert consume.status_code == 200
    assert consume.json()["access_token"]


async def test_magic_link_request_no_account_returns_202(
    client: AsyncClient, redis_client: Any, clean_identity: None
) -> None:
    """GIVEN no such user WHEN requesting magic-link THEN still 202 (anti-enumeration)."""
    r = await client.post(
        "/auth/magic-link/request", json={"email": "ghost@example.com"}
    )
    assert r.status_code == 202


async def test_password_reset_full_flow(
    client: AsyncClient, redis_client: Any, clean_identity: None, mailhog: AsyncClient
) -> None:
    """GIVEN a verified user WHEN running through password reset THEN new password works + old refresh gone."""
    email = _email()
    pw_old = "correct horse battery staple"
    pw_new = "rolling-stone-no-moss-pls"
    await _register_and_verify(client, mailhog, email, pw_old)
    login = await client.post("/auth/login", json={"email": email, "password": pw_old})
    assert login.status_code == 200
    await mailhog.delete("/api/v1/messages")

    req = await client.post("/auth/password-reset/request", json={"email": email})
    assert req.status_code == 202
    msgs = (await mailhog.get("/api/v2/messages")).json()
    token = _token_from_link(_link_from_mail(msgs["items"][0]["Content"]["Body"]))

    consume = await client.post(
        "/auth/password-reset/consume", json={"token": token, "password": pw_new}
    )
    assert consume.status_code == 200

    # Old refresh cookie now belongs to a revoked family; this MUST fail.
    r = await client.post("/auth/refresh", headers={"X-Refresh": "1"})
    assert r.status_code == 401

    # Login with the new password works.
    r = await client.post("/auth/login", json={"email": email, "password": pw_new})
    assert r.status_code == 200


# ─── OAuth dev bypass ──────────────────────────────────────────────────────


async def test_oauth_dev_bypass_disabled_by_default(client: AsyncClient) -> None:
    """GIVEN default settings WHEN GET /auth/oauth/dev/start THEN 404."""
    r = await client.get("/auth/oauth/dev/start", params={"email": _email()})
    assert r.status_code == 404


async def test_oauth_dev_bypass_enabled_creates_actor(
    client: AsyncClient,
    redis_client: Any,
    clean_identity: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN OAUTH_DEV_BYPASS=true WHEN GET /auth/oauth/dev/start?email=... THEN tokens issued."""
    monkeypatch.setattr(get_settings(), "oauth_dev_bypass", True)
    email = _email()
    r = await client.get("/auth/oauth/dev/start", params={"email": email})
    assert r.status_code == 200
    assert r.json()["access_token"]
    set_cookie = r.headers.get_list("set-cookie")
    assert any("refresh_token=" in c for c in set_cookie)
