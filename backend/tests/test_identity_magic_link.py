"""Magic-link mint + consume across all four purposes."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
import uuid_utils
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.identity.auth.magic_link import (
    PURPOSE_TTL,
    consume,
    find_active,
    mint,
)
from fastsaas.identity.models import (
    Actor,
    ActorType,
    MagicLinkPurpose,
    User,
)


async def _make_user(session: AsyncSession) -> Actor:
    actor = Actor(
        id=uuid_utils.uuid7(),
        actor_type=ActorType.HUMAN,
        display_name="ML Test",
    )
    session.add(actor)
    await session.flush()
    user = User(actor_id=actor.id, email=f"ml-{actor.id}@test.local")
    session.add(user)
    await session.flush()
    return actor


@pytest.mark.parametrize("purpose", list(MagicLinkPurpose))
async def test_mint_then_consume_round_trip(
    session: AsyncSession, purpose: MagicLinkPurpose
) -> None:
    """GIVEN a fresh actor WHEN a token is minted and consumed THEN it returns the row with consumed_at set."""
    actor = await _make_user(session)
    raw, row = await mint(session, actor_id=actor.id, purpose=purpose, email="user@test.local")

    consumed = await consume(session, raw_token=raw, purpose=purpose)

    assert consumed is not None
    assert consumed.token_hash == row.token_hash
    assert consumed.consumed_at is not None
    expected_ttl = PURPOSE_TTL[purpose]
    # Compare expires_at vs now (created_at is a server default not populated until commit).
    assert row.expires_at - datetime.now(UTC) <= expected_ttl + timedelta(seconds=2)


async def test_mint_persists_only_hash(session: AsyncSession) -> None:
    """GIVEN a minted token WHEN inspecting the DB row THEN the raw token never appears, only its sha256."""
    actor = await _make_user(session)
    raw, row = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )
    assert row.token_hash == hashlib.sha256(raw.encode()).hexdigest()
    assert raw not in row.token_hash
    assert len(raw) > 30  # ~43 chars from token_urlsafe(32)


async def test_consume_rejects_replay(session: AsyncSession) -> None:
    """GIVEN a consumed token WHEN consumed again THEN returns None."""
    actor = await _make_user(session)
    raw, _ = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.PASSWORD_RESET,
        email="user@test.local",
    )

    first = await consume(session, raw_token=raw, purpose=MagicLinkPurpose.PASSWORD_RESET)
    second = await consume(session, raw_token=raw, purpose=MagicLinkPurpose.PASSWORD_RESET)

    assert first is not None
    assert second is None


async def test_consume_rejects_expired(session: AsyncSession) -> None:
    """GIVEN a token with expires_at in the past WHEN consumed THEN returns None."""
    actor = await _make_user(session)
    raw, row = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )
    # Backdate. `row` IS used here — ruff's RUF059 false-positives on unpacking.
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.add(row)
    await session.flush()

    result = await consume(
        session, raw_token=raw, purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN
    )
    assert result is None


async def test_consume_rejects_unknown_token(session: AsyncSession) -> None:
    """GIVEN a token never minted WHEN consumed THEN returns None."""
    result = await consume(
        session,
        raw_token="not-a-real-token",
        purpose=MagicLinkPurpose.EMAIL_VERIFICATION,
    )
    assert result is None


async def test_consume_rejects_wrong_purpose(session: AsyncSession) -> None:
    """GIVEN a token minted for purpose A WHEN consumed as purpose B THEN returns None."""
    actor = await _make_user(session)
    raw, _ = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )

    result = await consume(
        session, raw_token=raw, purpose=MagicLinkPurpose.PASSWORD_RESET
    )
    assert result is None


async def test_consume_rolls_back_with_side_effect(session: AsyncSession) -> None:
    """GIVEN consume + a failing side effect WHEN the transaction rolls back THEN consumed_at is also reverted."""
    actor = await _make_user(session)
    raw, _row = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.EMAIL_VERIFICATION,
        email="user@test.local",
    )
    # Open a savepoint so we can roll back without disrupting the outer fixture transaction.
    async with session.begin_nested() as savepoint:
        consumed = await consume(
            session, raw_token=raw, purpose=MagicLinkPurpose.EMAIL_VERIFICATION
        )
        assert consumed is not None
        assert consumed.consumed_at is not None
        await savepoint.rollback()

    # After rollback the token is fresh again.
    refreshed = await find_active(
        session, raw_token=raw, purpose=MagicLinkPurpose.EMAIL_VERIFICATION
    )
    assert refreshed is not None
    assert refreshed.consumed_at is None


async def test_find_active_does_not_consume(session: AsyncSession) -> None:
    """GIVEN a fresh token WHEN find_active is called twice THEN it returns the same row both times."""
    actor = await _make_user(session)
    raw, _ = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )

    first = await find_active(
        session, raw_token=raw, purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN
    )
    second = await find_active(
        session, raw_token=raw, purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN
    )
    assert first is not None and second is not None
    assert first.token_hash == second.token_hash
    assert first.consumed_at is None and second.consumed_at is None


async def test_per_purpose_ttls_match_adr_008(session: AsyncSession) -> None:
    """GIVEN ADR-008 §8c WHEN inspecting PURPOSE_TTL THEN values match: 15min/24h/1h/7d."""
    assert PURPOSE_TTL[MagicLinkPurpose.MAGIC_LINK_LOGIN] == timedelta(minutes=15)
    assert PURPOSE_TTL[MagicLinkPurpose.EMAIL_VERIFICATION] == timedelta(hours=24)
    assert PURPOSE_TTL[MagicLinkPurpose.PASSWORD_RESET] == timedelta(hours=1)
    assert PURPOSE_TTL[MagicLinkPurpose.ORG_INVITATION] == timedelta(days=7)


async def test_two_mints_produce_distinct_tokens(session: AsyncSession) -> None:
    """GIVEN two mints for the same actor + purpose WHEN inspecting tokens THEN they differ."""
    actor = await _make_user(session)
    raw1, row1 = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )
    raw2, row2 = await mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email="user@test.local",
    )
    assert raw1 != raw2
    assert row1.token_hash != row2.token_hash
