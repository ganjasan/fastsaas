"""Integration tests for the GDPR PII scrub endpoint.

Drives the live ASGI app end-to-end and asserts:
- only the four PII keys are scrubbed; structural columns survive byte-for-byte
- compliance_officer (read-only) and plain members are 403-blocked
- wet scrubs append exactly one audit_scrub meta row in the same transaction
- dry-run returns the count without mutating and without writing a meta row
- re-running a scrub returns rows_scrubbed=0 but still logs the meta row
- cross-org isolation: DPO of acme cannot scrub globex's rows even with a
  matching actor_id filter
- scrubbed rows remain visible to compliance-officer cross-org reads (the
  structural row survives; only PII fields differ)

All tests use the live ASGI app fixture; the migrator session is used only
for direct DB peeks since RLS forbids the relevant SELECTs from `app_user`
without a pinned `app.current_org`.
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
from fastsaas.audit.scrub import SCRUBBED_GDPR_LITERAL
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
async def migrator_session() -> AsyncIterator[AsyncSession]:
    """A bypass-RLS migrator session for direct audit_log peek + scrub verify."""
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


async def _invite_and_accept(
    client: AsyncClient,
    mailhog: AsyncClient,
    *,
    owner_access: str,
    org_slug: str,
    invitee_email: str,
    invitee_password: str,
    role: str,
) -> str:
    """Invite an email under `role`, register the invitee, accept, return their access token."""
    r = await client.post(
        f"/orgs/{org_slug}/members/invite",
        json={"email": invitee_email, "role": role},
        headers={"Authorization": f"Bearer {owner_access}"},
    )
    assert r.status_code == 201, r.text
    msgs = (await mailhog.get("/api/v2/messages")).json()
    assert msgs["count"] >= 1
    invite_body = msgs["items"][0]["Content"]["Body"]
    invite_token = _token_from_link(_link_from_mail(invite_body))
    await mailhog.delete("/api/v1/messages")

    invitee_access = await _register_and_login(
        client, mailhog, invitee_email, invitee_password
    )
    r = await client.post(
        "/orgs/members/accept",
        json={"token": invite_token},
        headers={"Authorization": f"Bearer {invitee_access}"},
    )
    assert r.status_code == 200, r.text
    return invitee_access


async def _setup_org_with_dpo(
    client: AsyncClient, mailhog: AsyncClient, *, slug: str = "acme"
) -> tuple[str, UUID, str, UUID]:
    """Owner creates org, invites + accepts a DPO. Returns (owner_access,
    org_id, dpo_access, owner_actor_id)."""
    pw = "correct horse battery staple"
    owner_access = await _register_and_login(client, mailhog, _email(), pw)
    org_id = await _create_org(client, owner_access, slug, slug.title())
    # We want some audit rows generated by the OWNER's actions to scrub later.
    # Owner's actor_id is captured via a /orgs read.
    r = await client.get("/orgs", headers={"Authorization": f"Bearer {owner_access}"})
    assert r.status_code == 200
    owner_org = next(o for o in r.json() if o["slug"] == slug)
    owner_actor_id = UUID(owner_org["id"])  # NOTE: org id, not actor id
    # Pull actor_id from a fresh audit row of `member/create` for this org.
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT actor_id FROM audit_log "
                        "WHERE organisation_id = :oid "
                        "  AND entity_type = 'organisation' "
                        "  AND action = 'create' "
                        "ORDER BY timestamp ASC LIMIT 1"
                    ),
                    {"oid": str(org_id)},
                )
            ).one()
            owner_actor_id = UUID(str(row.actor_id))
    finally:
        await eng.dispose()

    dpo_access = await _invite_and_accept(
        client,
        mailhog,
        owner_access=owner_access,
        org_slug=slug,
        invitee_email=_email(),
        invitee_password=pw,
        role="dpo",
    )
    return owner_access, org_id, dpo_access, owner_actor_id


# ─── 6.3 — DPO scrubs by actor_id; only PII keys touched ───────────────────


async def test_dpo_scrubs_by_actor_id_only_touches_pii_keys(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN an owner with audit rows + a DPO in the same org
    _, org_id, dpo_access, owner_actor_id = await _setup_org_with_dpo(
        client, mailhog
    )
    # AND a captured baseline of the owner's audit rows (entity_type/action/diff)
    baseline = (
        await migrator_session.execute(
            text(
                "SELECT id, entity_type, entity_id, action, "
                "       intent_hash, diff, organisation_id "
                "FROM audit_log WHERE actor_id = :a AND organisation_id = :o "
                "ORDER BY timestamp"
            ),
            {"a": str(owner_actor_id), "o": str(org_id)},
        )
    ).all()
    assert len(baseline) >= 1, "expected owner-generated audit rows"

    # WHEN the DPO calls the scrub endpoint with actor_id filter (wet)
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is False
    assert body["rows_scrubbed"] == len(baseline)

    # THEN the four PII keys are replaced with the sentinel for every row
    after = (
        await migrator_session.execute(
            text(
                "SELECT id, entity_type, entity_id, action, intent_hash, "
                "       diff, organisation_id, intent_metadata "
                "FROM audit_log WHERE actor_id = :a AND organisation_id = :o"
            ),
            {"a": str(owner_actor_id), "o": str(org_id)},
        )
    ).all()
    assert len(after) == len(baseline)
    by_id = {row.id: row for row in after}
    for old in baseline:
        new = by_id[old.id]
        # Structural columns unchanged byte-for-byte
        assert new.entity_type == old.entity_type
        assert new.entity_id == old.entity_id
        assert new.action == old.action
        assert new.intent_hash == old.intent_hash
        assert new.diff == old.diff
        assert new.organisation_id == old.organisation_id
        # PII keys (when present) are now the sentinel
        md = new.intent_metadata
        for key in ("ip", "user_agent", "original_prompt", "path"):
            if key in md:
                assert md[key] == SCRUBBED_GDPR_LITERAL, (key, md)


# ─── 6.4 — compliance_officer (read-only) cannot scrub ────────────────────


async def test_compliance_officer_cannot_scrub(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN an org with a compliance_officer (read-only on audit_log)
    pw = "correct horse battery staple"
    owner_access = await _register_and_login(client, mailhog, _email(), pw)
    await _create_org(client, owner_access, "acme", "Acme")
    co_access = await _invite_and_accept(
        client,
        mailhog,
        owner_access=owner_access,
        org_slug="acme",
        invitee_email=_email(),
        invitee_password=pw,
        role="compliance_officer",
    )

    pre_count = (
        await migrator_session.execute(text("SELECT count(*) FROM audit_log"))
    ).scalar_one()

    # WHEN the compliance officer calls the scrub endpoint
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"ip": "203.0.113.4"}, "dry_run": False},
        headers={"Authorization": f"Bearer {co_access}"},
    )
    # THEN they are blocked with 403 authz.forbidden
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "authz.forbidden"

    # AND no row was modified — `audit_scrub` rows in particular weren't created
    post_count = (
        await migrator_session.execute(text("SELECT count(*) FROM audit_log"))
    ).scalar_one()
    assert post_count == pre_count

    # AND no audit_scrub rows exist
    scrub_rows = (
        await migrator_session.execute(
            text("SELECT count(*) FROM audit_log WHERE entity_type = 'audit_scrub'")
        )
    ).scalar_one()
    assert scrub_rows == 0


# ─── 6.5 — plain member cannot scrub ──────────────────────────────────────


async def test_plain_member_cannot_scrub(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
) -> None:
    # GIVEN an org with a plain member
    pw = "correct horse battery staple"
    owner_access = await _register_and_login(client, mailhog, _email(), pw)
    await _create_org(client, owner_access, "acme", "Acme")
    member_access = await _invite_and_accept(
        client,
        mailhog,
        owner_access=owner_access,
        org_slug="acme",
        invitee_email=_email(),
        invitee_password=pw,
        role="member",
    )

    # WHEN the member calls the scrub endpoint
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"ip": "203.0.113.4"}, "dry_run": False},
        headers={"Authorization": f"Bearer {member_access}"},
    )
    # THEN they are blocked with 403 authz.forbidden
    assert r.status_code == 403, r.text
    assert r.json()["detail"]["code"] == "authz.forbidden"


# ─── 6.6 — wet scrub appends one audit_scrub meta row ──────────────────────


async def test_wet_scrub_appends_meta_audit_row(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a DPO setup
    _, org_id, dpo_access, owner_actor_id = await _setup_org_with_dpo(client, mailhog)

    # WHEN the DPO performs a wet scrub
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r.status_code == 200
    rows_scrubbed = r.json()["rows_scrubbed"]

    # THEN exactly one audit_scrub meta row appended for this org
    scrubs = (
        await migrator_session.execute(
            text(
                "SELECT action, diff, intent_metadata "
                "FROM audit_log "
                "WHERE entity_type = 'audit_scrub' AND organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).all()
    assert len(scrubs) == 1
    meta = scrubs[0]
    assert meta.action == "scrub"
    assert meta.diff["after"]["rows_scrubbed"] == rows_scrubbed
    assert meta.diff["after"]["filter"]["actor_id"] == str(owner_actor_id)
    # And the DPO's own intent_metadata is recorded NOT scrubbed (legitimate
    # interest — DPO acts in professional capacity).
    assert meta.intent_metadata.get("path", "").startswith("/orgs/")
    assert "<scrubbed:gdpr>" not in str(meta.intent_metadata)


# ─── 6.7 — re-run is idempotent (rows=0 but meta row appended) ────────────


async def test_rerun_returns_zero_but_logs_meta(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a DPO who already performed a scrub
    _, org_id, dpo_access, owner_actor_id = await _setup_org_with_dpo(client, mailhog)
    r1 = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r1.status_code == 200
    first_count = r1.json()["rows_scrubbed"]
    assert first_count >= 1

    # WHEN the same scrub is re-run
    r2 = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    # THEN rows_scrubbed is 0 (data already erased) but the call succeeds
    assert r2.status_code == 200
    assert r2.json()["rows_scrubbed"] == 0

    # AND a SECOND meta row was appended — the DPO's repeat intent is logged
    scrub_count = (
        await migrator_session.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE entity_type = 'audit_scrub' AND organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).scalar_one()
    assert scrub_count == 2


# ─── 6.8 — cross-org isolation ────────────────────────────────────────────


async def test_dpo_of_acme_cannot_scrub_globex(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN orgs `acme` and `globex` each with audit rows
    pw = "correct horse battery staple"
    a_owner = await _register_and_login(client, mailhog, _email(), pw)
    a_org = await _create_org(client, a_owner, "acme", "Acme")
    b_owner = await _register_and_login(client, mailhog, _email(), pw)
    b_org = await _create_org(client, b_owner, "globex", "Globex")

    # AND a DPO on acme only
    dpo_access = await _invite_and_accept(
        client,
        mailhog,
        owner_access=a_owner,
        org_slug="acme",
        invitee_email=_email(),
        invitee_password=pw,
        role="dpo",
    )

    # AND we capture globex's pre-scrub intent_metadata to compare later
    globex_before = (
        await migrator_session.execute(
            text(
                "SELECT id, intent_metadata FROM audit_log "
                "WHERE organisation_id = :o ORDER BY timestamp"
            ),
            {"o": str(b_org)},
        )
    ).all()
    assert len(globex_before) >= 1

    # WHEN the acme-DPO calls scrub on /orgs/acme/audit/scrub with a filter
    # that COULD theoretically match globex's IPs/actor_ids
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"since": "2020-01-01T00:00:00Z"}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r.status_code == 200, r.text

    # THEN globex's rows are unchanged (the SQL is org-scoped to acme)
    globex_after = (
        await migrator_session.execute(
            text(
                "SELECT id, intent_metadata FROM audit_log "
                "WHERE organisation_id = :o ORDER BY timestamp"
            ),
            {"o": str(b_org)},
        )
    ).all()
    by_id_after = {row.id: row.intent_metadata for row in globex_after}
    for old in globex_before:
        assert by_id_after[old.id] == old.intent_metadata, (
            f"globex row {old.id} was mutated by acme DPO scrub"
        )
    # Sanity: acme has at least one row carrying the sentinel
    acme_scrubbed = (
        await migrator_session.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE organisation_id = :o "
                "  AND intent_metadata::text LIKE '%<scrubbed:gdpr>%'"
            ),
            {"o": str(a_org)},
        )
    ).scalar_one()
    assert acme_scrubbed >= 1


# ─── 6.9 — dry-run mutates nothing and writes no meta row ─────────────────


async def test_dry_run_returns_count_without_mutating_or_meta(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
    migrator_session: AsyncSession,
) -> None:
    # GIVEN a DPO setup
    _, org_id, dpo_access, owner_actor_id = await _setup_org_with_dpo(client, mailhog)
    pre_meta = (
        await migrator_session.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE entity_type = 'audit_scrub' AND organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).scalar_one()
    pre_text = (
        await migrator_session.execute(
            text(
                "SELECT string_agg(intent_metadata::text, '|' ORDER BY id) "
                "FROM audit_log WHERE organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).scalar_one()

    # WHEN the DPO calls the endpoint with dry_run=true
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": True},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dry_run"] is True
    assert body["rows_scrubbed"] >= 1

    # THEN no audit_scrub row was added
    post_meta = (
        await migrator_session.execute(
            text(
                "SELECT count(*) FROM audit_log "
                "WHERE entity_type = 'audit_scrub' AND organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).scalar_one()
    assert post_meta == pre_meta

    # AND no row's intent_metadata was modified
    post_text = (
        await migrator_session.execute(
            text(
                "SELECT string_agg(intent_metadata::text, '|' ORDER BY id) "
                "FROM audit_log WHERE organisation_id = :o"
            ),
            {"o": str(org_id)},
        )
    ).scalar_one()
    assert post_text == pre_text


# ─── 6.10 — scrubbed rows still visible to compliance-officer reads ───────


async def test_scrubbed_rows_remain_visible_under_compliance_officer_role(
    client: AsyncClient,
    redis_client: Any,
    wipe_state: None,
    mailhog: AsyncClient,
) -> None:
    # GIVEN an org with audit rows that have just been scrubbed
    _, org_id, dpo_access, owner_actor_id = await _setup_org_with_dpo(client, mailhog)
    r = await client.post(
        "/orgs/acme/audit/scrub",
        json={"filter": {"actor_id": str(owner_actor_id)}, "dry_run": False},
        headers={"Authorization": f"Bearer {dpo_access}"},
    )
    assert r.status_code == 200

    # WHEN we read audit_log under the compliance-officer GUC
    settings = get_settings()
    eng = create_async_engine(settings.database_url, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s, s.begin():
            await s.execute(
                text("SELECT set_config('app.role', 'compliance_officer', true)")
            )
            seen = (
                await s.execute(
                    text(
                        "SELECT count(*), "
                        "       count(*) FILTER (WHERE intent_metadata::text "
                        "                        LIKE '%<scrubbed:gdpr>%') "
                        "FROM audit_log WHERE organisation_id = :o"
                    ),
                    {"o": str(org_id)},
                )
            ).one()
        # THEN the structural rows survived (count > 0) AND at least some
        # carry the sentinel — compliance officer can still see "what
        # happened" even though the PII is gone.
        assert seen[0] >= 1
        assert seen[1] >= 1
    finally:
        await eng.dispose()
