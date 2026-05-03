"""ORM round-trip tests for identity models + CTI database invariants.

These verify that the SQLModel layer agrees with the migration-0001 schema
and that CTI CHECK constraints actually fire from app_user inserts.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import uuid_utils
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.identity.models import (
    Actor,
    ActorType,
    MagicLinkPurpose,
    MagicLinkToken,
    OAuthIdentity,
    User,
)


async def test_human_actor_round_trip(session: AsyncSession) -> None:
    """GIVEN a HUMAN actor and User WHEN inserted via ORM THEN both rows persist with defaults."""
    actor_id = uuid_utils.uuid7()
    actor = Actor(id=actor_id, actor_type=ActorType.HUMAN, display_name="Test User")
    session.add(actor)
    await session.flush()

    user = User(actor_id=actor_id, email=f"user-{actor_id}@test.local")
    session.add(user)
    await session.flush()

    fetched = await session.get(User, actor_id)
    assert fetched is not None
    assert fetched.email == f"user-{actor_id}@test.local"
    assert fetched.email_verified is False
    assert fetched.locale == "en"
    assert fetched.timezone == "UTC"


async def test_human_with_parent_rejected(session: AsyncSession) -> None:
    """GIVEN a HUMAN actor WHEN parent_actor_id is set THEN human_no_parent CHECK rejects."""
    parent = Actor(id=uuid_utils.uuid7(), actor_type=ActorType.HUMAN, display_name="Parent")
    session.add(parent)
    await session.flush()

    bad = Actor(
        id=uuid_utils.uuid7(),
        actor_type=ActorType.HUMAN,
        parent_actor_id=parent.id,
        display_name="Bad Human",
    )
    session.add(bad)
    with pytest.raises(IntegrityError, match="human_no_parent"):
        await session.flush()


async def test_invalid_actor_type_rejected(session: AsyncSession) -> None:
    """GIVEN an unknown actor_type WHEN inserted THEN actor_type_valid CHECK rejects."""
    with pytest.raises(IntegrityError, match="actor_type_valid"):
        await session.execute(
            text(
                "INSERT INTO actors (id, actor_type, display_name) "
                "VALUES (gen_random_uuid(), 'ROBOT', 'bad')"
            )
        )
        await session.flush()


async def test_oauth_identity_links_to_user(session: AsyncSession) -> None:
    """GIVEN a user WHEN an OAuthIdentity is added THEN it persists with composite PK."""
    actor = Actor(id=uuid_utils.uuid7(), actor_type=ActorType.HUMAN, display_name="OAuth User")
    session.add(actor)
    await session.flush()
    user = User(actor_id=actor.id, email=f"oauth-{actor.id}@test.local", email_verified=True)
    session.add(user)
    await session.flush()

    ident = OAuthIdentity(provider="google", provider_uid="g-12345", user_actor_id=actor.id)
    session.add(ident)
    await session.flush()

    fetched = await session.get(OAuthIdentity, {"provider": "google", "provider_uid": "g-12345"})
    assert fetched is not None
    assert fetched.user_actor_id == actor.id


async def test_magic_link_token_round_trip(session: AsyncSession) -> None:
    """GIVEN a magic-link token WHEN minted THEN it persists with derived expires_at."""
    actor = Actor(id=uuid_utils.uuid7(), actor_type=ActorType.HUMAN, display_name="ML User")
    session.add(actor)
    await session.flush()
    user = User(actor_id=actor.id, email=f"ml-{actor.id}@test.local")
    session.add(user)
    await session.flush()

    token = MagicLinkToken(
        token_hash=f"hash-{actor.id}",
        purpose=MagicLinkPurpose.EMAIL_VERIFICATION,
        actor_id=actor.id,
        email=user.email,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    session.add(token)
    await session.flush()

    fetched = await session.get(MagicLinkToken, f"hash-{actor.id}")
    assert fetched is not None
    assert fetched.purpose == MagicLinkPurpose.EMAIL_VERIFICATION
    assert fetched.consumed_at is None


async def test_magic_link_token_invalid_purpose_rejected(session: AsyncSession) -> None:
    """GIVEN an unknown purpose WHEN inserted via raw SQL THEN purpose CHECK rejects."""
    actor = Actor(id=uuid_utils.uuid7(), actor_type=ActorType.HUMAN, display_name="Bad Purpose")
    session.add(actor)
    await session.flush()

    with pytest.raises(IntegrityError, match="magic_link_purpose_valid"):
        await session.execute(
            text(
                "INSERT INTO magic_link_tokens "
                "(token_hash, purpose, actor_id, email, expires_at) "
                "VALUES ('h', 'unknown_purpose', :aid, 'x@x.com', NOW() + interval '1 hour')"
            ),
            {"aid": str(actor.id)},
        )
        await session.flush()
