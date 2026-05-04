"""Integration tests for the tenant_context dependency.

Exercises `_resolve_membership` against a real Postgres on the test stack
(run via `./run_test.sh`). Keeps its own setup_session fixture instead of
relying on `clean_identity` because the latter only wipes `actors` and the
new tables (`organisation_members`, `capabilities`) hold FK references that
would block actor cleanup.

`_migrator_engine` in `fastsaas.db` is module-level and would survive across
tests bound to a stale event loop; the autouse fixture resets it per test.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas import db as db_module
from fastsaas.authz.models import Capability
from fastsaas.config import get_settings
from fastsaas.identity.models import Actor, ActorType, User
from fastsaas.tenants.dependencies import _resolve_membership
from fastsaas.tenants.models import Organisation, OrganisationMember, OrganisationRole


@pytest.fixture(autouse=True)
async def _reset_migrator_engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    """Force `_resolve_membership` to build a fresh migrator engine each test.

    The module-level `_migrator_engine` would otherwise carry a connection
    pool bound to a closed event loop on the second test in the same file.
    """
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)
    yield
    if db_module._migrator_engine is not None:
        await db_module._migrator_engine.dispose()
    monkeypatch.setattr(db_module, "_migrator_engine", None, raising=False)
    monkeypatch.setattr(db_module, "_migrator_session_factory", None, raising=False)


@pytest.fixture
async def setup_session() -> AsyncIterator[AsyncSession]:
    """A BYPASSRLS session that wipes tenant + identity rows on entry AND exit.

    Wipes in dependency order so the next test starts from a clean slate
    even if a previous run left rows behind.
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
        async with factory() as s:
            yield s
        await wipe()
    finally:
        await eng.dispose()


async def _mk_actor(db: AsyncSession, *, email: str) -> UUID:
    actor = Actor(actor_type=ActorType.HUMAN, display_name=email)
    db.add(actor)
    await db.flush()
    db.add(User(actor_id=actor.id, email=email, email_verified=True))
    await db.flush()
    return actor.id


async def _mk_org(db: AsyncSession, *, slug: str, name: str = "") -> UUID:
    org = Organisation(name=name or slug, slug=slug)
    db.add(org)
    await db.flush()
    return org.id


class TestResolveMembership:
    async def test_unknown_slug_returns_none(self, setup_session: AsyncSession) -> None:
        # GIVEN an actor exists but no org with this slug exists
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="a@test.local")

        # WHEN _resolve_membership is called
        result = await _resolve_membership(slug="nonexistent", actor_id=actor_id)

        # THEN it returns None — caller turns that into 404 without leaking existence
        assert result is None

    async def test_member_returns_org_with_is_guest_false(
        self, setup_session: AsyncSession
    ) -> None:
        # GIVEN an actor is a member of org "acme"
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="m@test.local")
            org_id = await _mk_org(setup_session, slug="acme")
            setup_session.add(
                OrganisationMember(
                    organisation_id=org_id,
                    actor_id=actor_id,
                    role=OrganisationRole.MEMBER,
                )
            )

        # WHEN _resolve_membership is called
        result = await _resolve_membership(slug="acme", actor_id=actor_id)

        # THEN it returns the org with is_guest=False
        assert result is not None
        org, is_guest = result
        assert org.id == org_id
        assert is_guest is False

    async def test_non_member_with_no_capability_returns_none(
        self, setup_session: AsyncSession
    ) -> None:
        # GIVEN an actor exists, an org exists, another actor is a member of it,
        # but the first actor is neither a member nor a guest
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="x@test.local")
            org_id = await _mk_org(setup_session, slug="acme")
            other = await _mk_actor(setup_session, email="other@test.local")
            setup_session.add(
                OrganisationMember(
                    organisation_id=org_id,
                    actor_id=other,
                    role=OrganisationRole.OWNER,
                )
            )

        # WHEN _resolve_membership is called for the unrelated actor
        result = await _resolve_membership(slug="acme", actor_id=actor_id)

        # THEN None — same response as a missing org, by design (don't leak existence)
        assert result is None

    async def test_guest_with_project_capability_returns_is_guest_true(
        self, setup_session: AsyncSession
    ) -> None:
        # GIVEN an actor holds a project-scoped capability with metadata.org_id = acme.id
        # but no organisation_members row
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="g@test.local")
            org_id = await _mk_org(setup_session, slug="acme")
            granted_by = await _mk_actor(setup_session, email="grantor@test.local")
            setup_session.add(
                Capability(
                    actor_id=actor_id,
                    operation="read",
                    resource_type="project",
                    resource_id=uuid4(),
                    bundle_name="role:guest_viewer",
                    granted_by=granted_by,
                    meta={"org_id": str(org_id)},
                )
            )

        # WHEN _resolve_membership is called
        result = await _resolve_membership(slug="acme", actor_id=actor_id)

        # THEN it returns the org with is_guest=True
        assert result is not None
        org, is_guest = result
        assert org.id == org_id
        assert is_guest is True

    async def test_revoked_capability_does_not_grant_guest_access(
        self, setup_session: AsyncSession
    ) -> None:
        # GIVEN a guest's capability has been revoked
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="ex@test.local")
            org_id = await _mk_org(setup_session, slug="acme")
            granted_by = await _mk_actor(setup_session, email="grantor2@test.local")
            setup_session.add(
                Capability(
                    actor_id=actor_id,
                    operation="read",
                    resource_type="project",
                    resource_id=uuid4(),
                    bundle_name="role:guest_viewer",
                    granted_by=granted_by,
                    revoked_at=datetime.now(UTC),
                    meta={"org_id": str(org_id)},
                )
            )

        # WHEN _resolve_membership is called
        result = await _resolve_membership(slug="acme", actor_id=actor_id)

        # THEN the revoked capability is ignored — actor cannot reach the org
        assert result is None

    async def test_soft_deleted_org_is_invisible(
        self, setup_session: AsyncSession
    ) -> None:
        # GIVEN an org has been soft-deleted
        async with setup_session.begin():
            actor_id = await _mk_actor(setup_session, email="sd@test.local")
            org = Organisation(name="Acme", slug="acme", deleted_at=datetime.now(UTC))
            setup_session.add(org)
            await setup_session.flush()
            setup_session.add(
                OrganisationMember(
                    organisation_id=org.id,
                    actor_id=actor_id,
                    role=OrganisationRole.OWNER,
                )
            )

        # WHEN _resolve_membership is called
        result = await _resolve_membership(slug="acme", actor_id=actor_id)

        # THEN the soft-deleted org is not visible even to its owner
        assert result is None
