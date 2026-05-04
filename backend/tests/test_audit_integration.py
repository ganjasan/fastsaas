"""Integration tests for the audit core.

Drives the live ASGI app end-to-end and asserts:
- every core mutation produces the documented audit_log rows
  (Phase 5.4 from openspec/changes/audit-trail-middleware/tasks.md);
- sensitive fields never appear in audit_log.diff (5.5);
- the RLS read path: members see only their org, compliance_officer
  sees cross-org via the `app.role` GUC (5.6);
- end-to-end smoke: org create + project create produce the expected
  audit rows visible via direct DB peek (5.7).
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
from fastsaas.audit.redact import REDACTED_LITERAL
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
            await s.execute(text("DELETE FROM audit_log"))
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


@pytest.fixture
async def migrator_session() -> AsyncIterator[AsyncSession]:
    """A bypass-RLS migrator session for direct audit_log peek."""
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
) -> str:
    """Register → consume verification → login → return Bearer access token."""
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


async def _create_org(client: AsyncClient, access: str, slug: str, name: str) -> UUID:
    r = await client.post(
        "/orgs",
        json={"name": name, "slug": slug},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    return UUID(r.json()["id"])


# ─── 5.4 / 5.7 — every core mutation produces the right audit rows ──────────


async def test_create_org_writes_organisation_and_capability_audit_rows(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a verified user with an access token
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)

    # WHEN they POST /orgs to create "acme"
    org_id = await _create_org(client, access, "acme", "Acme")

    # THEN exactly one organisation/create audit row exists for the org
    result = await migrator_session.execute(
        text(
            "SELECT entity_type, action, organisation_id "
            "FROM audit_log WHERE entity_type = 'organisation' AND entity_id = :oid"
        ),
        {"oid": str(org_id)},
    )
    rows = result.all()
    assert len(rows) == 1, rows
    assert rows[0].action == "create"
    assert rows[0].organisation_id == org_id

    # AND at least one capability/create audit row for the role:owner mint
    cap_rows = (
        await migrator_session.execute(
            text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE entity_type = 'capability' "
                "  AND action = 'create' "
                "  AND organisation_id = :oid"
            ),
            {"oid": str(org_id)},
        )
    ).scalar_one()
    assert cap_rows >= 1


async def test_create_project_writes_project_audit_row_with_org_id_metadata(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a verified owner of an org
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    org_id = await _create_org(client, access, "acme", "Acme")

    # WHEN they POST /orgs/acme/projects to create a project
    r = await client.post(
        "/orgs/acme/projects",
        json={"name": "Q4 Plan", "slug": "q4-plan", "description": None},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    project_id = UUID(r.json()["id"])

    # THEN exactly one project/create audit row exists for the project
    rows = (
        await migrator_session.execute(
            text(
                "SELECT action, organisation_id, intent_metadata "
                "FROM audit_log WHERE entity_type = 'project' AND entity_id = :pid"
            ),
            {"pid": str(project_id)},
        )
    ).all()
    assert len(rows) == 1, rows
    assert rows[0].action == "create"
    assert rows[0].organisation_id == org_id
    # AND intent_metadata carries org_id + project_id for cross-cutting filters
    md = rows[0].intent_metadata
    assert md["org_id"] == str(org_id)
    assert md["project_id"] == str(project_id)


# ─── 5.5 — sensitive fields never reach audit_log.diff ──────────────────────


async def test_audit_diff_never_contains_password_hash(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a verified user who creates an org (which mints capabilities,
    # owner membership, etc. — a fan-out across multiple audit rows)
    pw = "correct horse battery staple"
    access = await _register_and_login(client, mailhog, _email(), pw)
    await _create_org(client, access, "acme", "Acme")

    # WHEN we cast every audit_log.diff back to text and grep for any
    # of the global denylist names appearing as RAW (non-redacted) values
    rows = (
        await migrator_session.execute(text("SELECT diff::text AS diff_text FROM audit_log"))
    ).all()

    # THEN no diff carries a non-redacted secret. The presence-of-key
    # invariant means the denylist key may still appear, but only paired
    # with the literal "<redacted>". A smoke pattern that catches both
    # cases: search for password_hash that is NOT followed by "<redacted>".
    secret_pattern = re.compile(
        r'"(password_hash|token_hash|api_key_hash|key_hash|client_secret|raw_token)"\s*:\s*"(?!<redacted>)'
    )
    for (diff_text,) in rows:
        assert not secret_pattern.search(diff_text), (
            f"secret leaked into audit diff: {diff_text!r}"
        )


# ─── 5.6 — RLS read path: tenant scope vs compliance officer escape ────────


async def test_audit_log_rls_member_only_sees_own_org(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
) -> None:
    # GIVEN two distinct verified users, each owning one org with audit rows
    pw = "correct horse battery staple"
    a_access = await _register_and_login(client, mailhog, _email(), pw)
    a_org = await _create_org(client, a_access, "acme", "Acme")
    b_access = await _register_and_login(client, mailhog, _email(), pw)
    b_org = await _create_org(client, b_access, "globex", "Globex")
    assert a_org != b_org

    # WHEN we read audit_log as the app_user role with app.current_org pinned
    # to acme — RLS should hide globex rows entirely.
    settings = get_settings()
    eng = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s, s.begin():
            await s.execute(text(f"SET LOCAL app.current_org = '{a_org}'"))
            seen = (
                await s.execute(text("SELECT DISTINCT organisation_id FROM audit_log"))
            ).scalars().all()
        # THEN only the acme org's rows are returned
        seen_uuids = {row for row in seen if row is not None}
        assert seen_uuids <= {a_org}
    finally:
        await eng.dispose()


async def test_compliance_officer_role_unlocks_cross_org_audit_reads(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
) -> None:
    # GIVEN two orgs each with their own audit rows
    pw = "correct horse battery staple"
    a_access = await _register_and_login(client, mailhog, _email(), pw)
    a_org = await _create_org(client, a_access, "acme", "Acme")
    b_access = await _register_and_login(client, mailhog, _email(), pw)
    b_org = await _create_org(client, b_access, "globex", "Globex")

    # WHEN we read audit_log under the compliance-officer GUC (no current_org)
    settings = get_settings()
    eng = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s, s.begin():
            await s.execute(text("SELECT set_config('app.role', 'compliance_officer', true)"))
            seen = (
                await s.execute(text("SELECT DISTINCT organisation_id FROM audit_log"))
            ).scalars().all()
        # THEN both orgs' rows are visible
        seen_uuids = {row for row in seen if row is not None}
        assert {a_org, b_org} <= seen_uuids
    finally:
        await eng.dispose()
