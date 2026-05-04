"""Jinja2-rendered identity emails delivered via aiosmtplib.

Per design.md §D7: render synchronously from packaged templates, send
asynchronously. In dev the SMTP host points at Mailhog (`localhost:1125` —
FastSaaS uses the +100 host-port shift; no auth, plaintext); production swaps
host/port + credentials only.

Each `send_*` helper takes the recipient and the *raw* magic-link token
(NOT the hash); it embeds the token in a URL anchored on `app_url` and
fires off a multipart/alternative message (text + html).
"""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import aiosmtplib
from jinja2 import Environment, FileSystemLoader

from fastsaas.config import get_settings

_TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


def _autoescape(template_name: str | None) -> bool:
    """Escape only `.html.j2` templates; `.txt.j2` is plain text and must not be escaped."""
    return template_name is not None and ".html" in template_name


_env = Environment(
    loader=FileSystemLoader(_TEMPLATE_DIR),
    autoescape=_autoescape,
    keep_trailing_newline=False,
)


def _build_url(path: str, token: str) -> str:
    """Compose `<app_url><path>/<token>`, normalising trailing slashes."""
    base = get_settings().app_url.rstrip("/")
    return f"{base}{path}/{token}"


def render(template: str, **ctx: object) -> tuple[str, str]:
    """Render `<template>.txt.j2` + `<template>.html.j2` with `ctx`. Returns `(text, html)`."""
    txt = _env.get_template(f"{template}.txt.j2").render(**ctx)
    html = _env.get_template(f"{template}.html.j2").render(**ctx)
    return txt, html


async def send(*, to: str, subject: str, template: str, **ctx: object) -> None:
    """Render the named template and dispatch via SMTP. Caller passes context vars as kwargs."""
    settings = get_settings()
    text, html = render(template, **ctx)
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user or None,
        password=settings.smtp_password or None,
        use_tls=False,
        start_tls=False,
    )


async def send_verification(to: str, raw_token: str) -> None:
    """Verify-email link, valid 24h."""
    name = get_settings().app_name
    await send(
        to=to,
        subject=f"Verify your email — {name}",
        template="verification",
        url=_build_url("/auth/verify-email", raw_token),
        app_name=name,
    )


async def send_magic_link(to: str, raw_token: str) -> None:
    """Single-use sign-in link, valid 15 min."""
    name = get_settings().app_name
    await send(
        to=to,
        subject=f"Your {name} sign-in link",
        template="magic_link_login",
        url=_build_url("/auth/magic-link", raw_token),
        app_name=name,
    )


async def send_password_reset(to: str, raw_token: str) -> None:
    """Password-reset link, valid 1 h."""
    name = get_settings().app_name
    await send(
        to=to,
        subject=f"Reset your {name} password",
        template="password_reset",
        url=_build_url("/auth/reset-password", raw_token),
        app_name=name,
    )


async def send_org_invitation(
    to: str, raw_token: str, *, org_name: str, inviter_email: str
) -> None:
    """Org-invite link, valid 7 days. The accept page lives at
    `/orgs/accept-invite/<token>` on the SPA; the backend exposes the
    matching `POST /orgs/{slug}/members/accept` endpoint."""
    name = get_settings().app_name
    await send(
        to=to,
        subject=f"You're invited to {org_name} on {name}",
        template="org_invitation",
        url=_build_url("/orgs/accept-invite", raw_token),
        app_name=name,
        org_name=org_name,
        inviter_email=inviter_email,
    )


async def send_project_share(
    to: str,
    raw_token: str,
    *,
    org_name: str,
    project_name: str,
    inviter_email: str,
    ttl_days: int,
) -> None:
    """Per-project guest invite (UC-001). The accept page lives at
    `/orgs/accept-share/<token>` on the SPA; the backend route is
    `POST /orgs/projects/accept-share` (token in body)."""
    name = get_settings().app_name
    await send(
        to=to,
        subject=f"{inviter_email} shared {project_name} on {name}",
        template="project_share",
        url=_build_url("/orgs/accept-share", raw_token),
        app_name=name,
        org_name=org_name,
        project_name=project_name,
        inviter_email=inviter_email,
        ttl_days=ttl_days,
    )
