"""Refresh-family Redis tracking — rotation, reuse detection, revocation."""

from __future__ import annotations

from uuid import uuid4

import pytest
from redis.asyncio import Redis

from fastsaas.identity.auth.refresh import (
    RefreshReusedError,
    RefreshUnknownError,
    get_current_jti,
    revoke_all_for_actor,
    revoke_family,
    rotate,
    start_family,
)


async def test_start_family_persists_state(redis_client: Redis) -> None:
    """GIVEN a fresh actor WHEN start_family is called THEN family hash and actor index are written."""
    actor_id = uuid4()
    family_id, jti = await start_family(actor_id)

    stored_jti = await redis_client.hget(f"refresh:fam:{family_id}", "current_jti")
    stored_actor = await redis_client.hget(f"refresh:fam:{family_id}", "user_actor_id")
    in_actor_index = await redis_client.sismember(f"refresh:actor:{actor_id}", str(family_id))

    assert stored_jti == str(jti)
    assert stored_actor == str(actor_id)
    assert bool(in_actor_index) is True


async def test_rotate_with_current_jti_succeeds(redis_client: Redis) -> None:
    """GIVEN a family WHEN rotate is called with the current jti THEN a new jti is returned."""
    actor_id = uuid4()
    family_id, jti1 = await start_family(actor_id)

    jti2 = await rotate(family_id, jti1, actor_id)

    assert jti2 != jti1
    current = await get_current_jti(family_id)
    assert current == jti2


async def test_rotate_with_old_jti_raises_reused_and_revokes(redis_client: Redis) -> None:
    """GIVEN a rotated family WHEN replaying the old jti THEN RefreshReusedError raises and family is gone."""
    actor_id = uuid4()
    family_id, jti1 = await start_family(actor_id)
    await rotate(family_id, jti1, actor_id)

    with pytest.raises(RefreshReusedError):
        await rotate(family_id, jti1, actor_id)

    # Family is deleted; subsequent rotations are unknown.
    assert await get_current_jti(family_id) is None
    in_index = await redis_client.sismember(f"refresh:actor:{actor_id}", str(family_id))
    assert bool(in_index) is False


async def test_rotate_unknown_family_raises_unknown(redis_client: Redis) -> None:
    """GIVEN no family WHEN rotate is called THEN RefreshUnknownError raises."""
    with pytest.raises(RefreshUnknownError):
        await rotate(uuid4(), uuid4(), uuid4())


async def test_revoke_family_deletes_state(redis_client: Redis) -> None:
    """GIVEN a family WHEN revoke_family is called THEN both hash and actor index entry are gone."""
    actor_id = uuid4()
    family_id, _ = await start_family(actor_id)

    await revoke_family(family_id, actor_id)

    assert await get_current_jti(family_id) is None
    in_index = await redis_client.sismember(f"refresh:actor:{actor_id}", str(family_id))
    assert bool(in_index) is False


async def test_revoke_all_for_actor_wipes_every_family(redis_client: Redis) -> None:
    """GIVEN multiple families for one actor WHEN revoke_all_for_actor is called THEN all are deleted."""
    actor_id = uuid4()
    fam_a, _ = await start_family(actor_id)
    fam_b, _ = await start_family(actor_id)
    fam_c, _ = await start_family(actor_id)

    count = await revoke_all_for_actor(actor_id)

    assert count == 3
    assert await get_current_jti(fam_a) is None
    assert await get_current_jti(fam_b) is None
    assert await get_current_jti(fam_c) is None
    assert await redis_client.exists(f"refresh:actor:{actor_id}") == 0


async def test_revoke_all_for_actor_with_no_families_is_noop(redis_client: Redis) -> None:
    """GIVEN an actor with no families WHEN revoke_all_for_actor is called THEN it returns 0."""
    count = await revoke_all_for_actor(uuid4())
    assert count == 0


async def test_chain_of_rotations_keeps_history_consistent(redis_client: Redis) -> None:
    """GIVEN repeated valid rotations WHEN each presents the immediately-previous jti THEN they all succeed."""
    actor_id = uuid4()
    family_id, jti = await start_family(actor_id)

    for _ in range(5):
        new_jti = await rotate(family_id, jti, actor_id)
        assert new_jti != jti
        jti = new_jti

    assert await get_current_jti(family_id) == jti


async def test_reuse_after_chain_blacklists_family(redis_client: Redis) -> None:
    """GIVEN a long chain WHEN any earlier jti is replayed THEN reuse is detected and family is gone."""
    actor_id = uuid4()
    family_id, jti0 = await start_family(actor_id)
    jti1 = await rotate(family_id, jti0, actor_id)
    jti2 = await rotate(family_id, jti1, actor_id)

    with pytest.raises(RefreshReusedError):
        await rotate(family_id, jti1, actor_id)

    # Even the most-recent jti can no longer rotate — family is gone.
    with pytest.raises(RefreshUnknownError):
        await rotate(family_id, jti2, actor_id)
