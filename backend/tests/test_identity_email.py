"""Identity email rendering + SMTP delivery, asserted via Mailhog HTTP API.

Mailhog runs in docker-compose (SMTP :1025, HTTP :8025). The fixture flushes
its message store at start so each test sees only its own send. Skips when
Mailhog isn't reachable so unit-only environments still pass.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from fastsaas.config import get_settings
from fastsaas.identity.email import (
    render,
    send_magic_link,
    send_password_reset,
    send_verification,
)

MAILHOG_HTTP = "http://localhost:8025"


async def _mailhog_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.5) as c:
            r = await c.get(f"{MAILHOG_HTTP}/api/v2/messages")
            return r.status_code == 200
    except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
        return False


@pytest.fixture
async def mailhog() -> AsyncIterator[httpx.AsyncClient]:
    if not await _mailhog_reachable():
        pytest.skip("Mailhog is not reachable on localhost:8025")
    async with httpx.AsyncClient(base_url=MAILHOG_HTTP, timeout=5) as c:
        await c.delete("/api/v1/messages")
        yield c
        await c.delete("/api/v1/messages")


def test_render_returns_text_and_html() -> None:
    """GIVEN a template + url WHEN rendered THEN both versions contain the URL substring."""
    text, html = render("verification", url="https://app.test/auth/verify-email/ABC")
    assert "https://app.test/auth/verify-email/ABC" in text
    assert "https://app.test/auth/verify-email/ABC" in html
    assert "<a" in html  # html version actually has markup


def test_render_escapes_html_in_url() -> None:
    """GIVEN a URL containing markup WHEN rendered THEN the html template escapes it."""
    text, html = render("verification", url="https://app.test/x?<script>=1")
    # The text version is allowed to contain the raw value; the html one must not.
    assert "<script>" in text
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


async def test_send_verification_arrives_at_mailhog(
    mailhog: httpx.AsyncClient,
) -> None:
    """GIVEN a verification email is sent WHEN Mailhog is polled THEN subject + recipient + URL appear."""
    await send_verification("verify@test.local", "VERIFICATION-TOKEN-RAW")

    res = (await mailhog.get("/api/v2/messages")).json()
    assert res["count"] == 1
    msg = res["items"][0]
    # Subject contains the em-dash, which SMTP encodes via RFC 2047; check substrings.
    subject = msg["Content"]["Headers"]["Subject"][0]
    assert "Verify your email" in subject
    assert get_settings().app_name in subject
    assert msg["Content"]["Headers"]["To"][0] == "verify@test.local"
    base = get_settings().app_url.rstrip("/")
    assert f"{base}/auth/verify-email/VERIFICATION-TOKEN-RAW" in msg["Content"]["Body"]


async def test_send_magic_link_uses_correct_path(mailhog: httpx.AsyncClient) -> None:
    """GIVEN a magic-link email is sent WHEN Mailhog is polled THEN body contains /auth/magic-link/<token>."""
    await send_magic_link("login@test.local", "MAGIC-LINK-RAW")

    res = (await mailhog.get("/api/v2/messages")).json()
    assert res["count"] == 1
    body = res["items"][0]["Content"]["Body"]
    base = get_settings().app_url.rstrip("/")
    assert f"{base}/auth/magic-link/MAGIC-LINK-RAW" in body
    subject = res["items"][0]["Content"]["Headers"]["Subject"][0]
    assert "sign-in" in subject.lower()


async def test_send_password_reset_uses_correct_path(
    mailhog: httpx.AsyncClient,
) -> None:
    """GIVEN a password-reset email is sent WHEN Mailhog is polled THEN body contains /auth/reset-password/<token>."""
    await send_password_reset("reset@test.local", "RESET-RAW")

    res = (await mailhog.get("/api/v2/messages")).json()
    assert res["count"] == 1
    body = res["items"][0]["Content"]["Body"]
    base = get_settings().app_url.rstrip("/")
    assert f"{base}/auth/reset-password/RESET-RAW" in body
    name = get_settings().app_name
    assert (
        f"Reset your {name} password"
        in res["items"][0]["Content"]["Headers"]["Subject"][0]
    )


async def test_send_carries_multipart_alternative(
    mailhog: httpx.AsyncClient,
) -> None:
    """GIVEN any send WHEN inspected THEN the message has both text/plain and text/html parts."""
    await send_verification("multipart@test.local", "TOK")
    res = (await mailhog.get("/api/v2/messages")).json()
    msg = res["items"][0]
    content_type = msg["Content"]["Headers"]["Content-Type"][0]
    assert "multipart/alternative" in content_type
