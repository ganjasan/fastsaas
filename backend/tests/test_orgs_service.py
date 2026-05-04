"""Service-layer tests for OrganisationService.

Sits below the API tests: fewer fixtures (no auth, no Mailhog), exercises the
service contract directly. Mostly there to hit edge cases that are awkward
to provoke through the live API — concurrency, in particular.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from fastsaas import db as db_module
from fastsaas.audit.context import set_audit_context
from fastsaas.config import get_settings
from fastsaas.identity.models import Actor, ActorType, User
from fastsaas.identity.schemas import CurrentActor
from fastsaas.tenants.service import OrganisationService, OrgSlugTakenError


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


async def _mk_actor(email: str) -> UUID:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as s, s.begin():
            actor = Actor(actor_type=ActorType.HUMAN, display_name=email)
            s.add(actor)
            await s.flush()
            s.add(User(actor_id=actor.id, email=email, email_verified=True))
            await s.flush()
            return actor.id
    finally:
        await eng.dispose()


def _synth_actor(actor_id: UUID, email: str) -> CurrentActor:
    """Construct a `CurrentActor` for tests that exercise the service layer
    directly (no HTTP middleware to populate `actor_var`). The audit core
    requires `actor_var` set on every mutation; this factory + the
    `set_audit_context` context manager satisfy that contract without
    mocking the JWT path."""
    return CurrentActor(
        actor_id=actor_id,
        actor_type=ActorType.HUMAN,
        parent_actor_id=None,
        email=email,
        email_verified=True,
    )


async def _create_org_as(
    actor_id: UUID, email: str, *, name: str, slug: str
):
    with set_audit_context(_synth_actor(actor_id, email)):
        return await OrganisationService.create(
            name=name, slug=slug, owner_actor_id=actor_id
        )


class TestCreateOrgConcurrency:
    async def test_concurrent_same_slug_yields_one_409_one_success(
        self, wipe_state: None
    ) -> None:
        # GIVEN two distinct actors racing to create an org with the same slug
        a = await _mk_actor("a@example.com")
        b = await _mk_actor("b@example.com")

        # WHEN both call OrganisationService.create concurrently
        results = await asyncio.gather(
            _create_org_as(a, "a@example.com", name="A", slug="contended"),
            _create_org_as(b, "b@example.com", name="B", slug="contended"),
            return_exceptions=True,
        )

        # THEN exactly one wins, the other receives OrgSlugTakenError —
        # never an unwrapped IntegrityError that would 500 at the API.
        successes = [r for r in results if not isinstance(r, BaseException)]
        failures = [r for r in results if isinstance(r, BaseException)]
        assert len(successes) == 1, results
        assert len(failures) == 1, results
        assert isinstance(failures[0], OrgSlugTakenError), failures[0]
