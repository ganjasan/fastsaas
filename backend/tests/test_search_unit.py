"""Unit tests for the search foundation — registry + orchestrator.

DB-touching scenarios live in `test_api_search.py`. This file exercises
the pure-Python contract: duplicate registration is rejected, the
orchestrator skips providers whose `is_visible` returns False, and a
provider that raises in `search()` is omitted from the response without
bringing down the rest.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest

from fastsaas.identity.schemas import ActorType, CurrentActor
from fastsaas.search import (
    SearchHit,
    SearchProviderConflictError,
    register_provider,
    search_all,
)
from fastsaas.search.registry import _PROVIDERS, _reset_for_tests


@pytest.fixture
async def fresh_registry() -> AsyncIterator[None]:
    """Snapshot + restore the registry around each test so tests can
    add/remove providers without leaking into the others."""
    snapshot = dict(_PROVIDERS)
    _reset_for_tests()
    yield
    _reset_for_tests()
    _PROVIDERS.update(snapshot)


def _actor() -> CurrentActor:
    return CurrentActor(
        actor_id=uuid4(),
        actor_type=ActorType.HUMAN,
        parent_actor_id=None,
        email="actor@example.com",
        email_verified=True,
    )


class _FakeProvider:
    def __init__(
        self,
        *,
        entity_type: str = "fake",
        label: str = "Fake",
        visible: bool = True,
        visibility_raises: BaseException | None = None,
        hits: list[SearchHit] | None = None,
        raises: BaseException | None = None,
    ) -> None:
        self.entity_type = entity_type
        self.label = label
        self._visible = visible
        self._visibility_raises = visibility_raises
        self._hits = hits or []
        self._raises = raises
        self.calls: list[tuple[str, UUID]] = []

    async def is_visible(self, *, actor, org_id, is_guest, db, cache) -> bool:
        if self._visibility_raises is not None:
            raise self._visibility_raises
        return self._visible

    async def search(
        self, *, query: str, actor: CurrentActor, org_id: UUID, limit: int, db
    ) -> list[SearchHit]:
        self.calls.append((query, org_id))
        if self._raises is not None:
            raise self._raises
        return self._hits[:limit]


class TestRegistry:
    def test_duplicate_entity_type_rejected(self, fresh_registry: None) -> None:
        # GIVEN a provider already registered for entity_type "alpha"
        first = _FakeProvider(entity_type="alpha")
        register_provider(first)
        # WHEN a second provider tries to claim the same entity_type
        # THEN the registry raises a clear conflict error so the bug surfaces
        # at module-load time, not silently overwrites the first registration
        second = _FakeProvider(entity_type="alpha", label="Alpha duplicate")
        with pytest.raises(SearchProviderConflictError) as exc_info:
            register_provider(second)
        assert "alpha" in str(exc_info.value)


class TestServiceOrchestrator:
    @pytest.mark.asyncio
    async def test_provider_skipped_when_is_visible_returns_false(
        self, fresh_registry: None
    ) -> None:
        # GIVEN two providers — one visible, one not
        passing = _FakeProvider(
            entity_type="passing",
            visible=True,
            hits=[
                SearchHit(
                    entity_type="passing",
                    entity_id=uuid4(),
                    title="hit",
                    href="/hit",
                )
            ],
        )
        failing = _FakeProvider(entity_type="failing", visible=False)
        register_provider(passing)
        register_provider(failing)
        # WHEN search_all runs
        # THEN only the visible provider runs and contributes a group
        org_id = uuid4()
        res = await search_all(
            actor=_actor(),
            org_id=org_id,
            is_guest=False,
            q="hit",
            kinds=None,
            db=None,
            cache=None,
        )

        assert [g.entity_type for g in res.groups] == ["passing"]
        # Confirm the failing provider's `search` was never invoked.
        assert failing.calls == []
        assert passing.calls == [("hit", org_id)]

    @pytest.mark.asyncio
    async def test_is_visible_exception_skips_provider(
        self, fresh_registry: None
    ) -> None:
        # GIVEN a provider whose is_visible() raises (e.g. a downstream bug
        # leaking through can()) and one that returns hits normally
        broken = _FakeProvider(
            entity_type="broken",
            visibility_raises=RuntimeError("authz blew up"),
        )
        ok = _FakeProvider(
            entity_type="ok",
            hits=[SearchHit(entity_type="ok", entity_id=uuid4(), title="hit", href="/hit")],
        )
        register_provider(broken)
        register_provider(ok)
        # WHEN search_all runs
        # THEN broken provider is silently skipped and the rest of the
        # response returns normally — the palette degrades, never errors out
        res = await search_all(
            actor=_actor(),
            org_id=uuid4(),
            is_guest=False,
            q="hit",
            kinds=None,
            db=None,
            cache=None,
        )
        assert [g.entity_type for g in res.groups] == ["ok"]
        assert broken.calls == []

    @pytest.mark.asyncio
    async def test_search_exception_is_swallowed(self, fresh_registry: None) -> None:
        # GIVEN one provider whose search() raises and one that returns hits
        raising = _FakeProvider(entity_type="boom", raises=RuntimeError("nope"))
        ok = _FakeProvider(
            entity_type="ok",
            hits=[
                SearchHit(
                    entity_type="ok",
                    entity_id=uuid4(),
                    title="hit",
                    href="/hit",
                )
            ],
        )
        register_provider(raising)
        register_provider(ok)
        # WHEN search_all runs
        # THEN the failing group is omitted but the rest of the response is normal
        res = await search_all(
            actor=_actor(),
            org_id=uuid4(),
            is_guest=False,
            q="hit",
            kinds=None,
            db=None,
            cache=None,
        )
        assert [g.entity_type for g in res.groups] == ["ok"]

    @pytest.mark.asyncio
    async def test_kinds_filter_narrows_providers(self, fresh_registry: None) -> None:
        # GIVEN three providers
        a = _FakeProvider(entity_type="a", hits=[SearchHit(entity_type="a", entity_id=uuid4(), title="A", href="/a")])
        b = _FakeProvider(entity_type="b", hits=[SearchHit(entity_type="b", entity_id=uuid4(), title="B", href="/b")])
        c = _FakeProvider(entity_type="c", hits=[SearchHit(entity_type="c", entity_id=uuid4(), title="C", href="/c")])
        for p in (a, b, c):
            register_provider(p)
        # WHEN kinds=["a", "c"]
        # THEN only those providers run; "b" is skipped before the gate even fires
        res = await search_all(
            actor=_actor(),
            org_id=uuid4(),
            is_guest=False,
            q="x",
            kinds=["a", "c"],
            db=None,
            cache=None,
        )
        assert {g.entity_type for g in res.groups} == {"a", "c"}
        assert b.calls == []

    @pytest.mark.asyncio
    async def test_empty_groups_omitted(self, fresh_registry: None) -> None:
        # GIVEN a visible provider that returns zero hits
        empty = _FakeProvider(entity_type="empty", hits=[])
        register_provider(empty)
        # WHEN search_all runs
        # THEN the response.groups list is empty (we don't surface a vacuous group)
        res = await search_all(
            actor=_actor(),
            org_id=uuid4(),
            is_guest=False,
            q="x",
            kinds=None,
            db=None,
            cache=None,
        )
        assert res.groups == []
