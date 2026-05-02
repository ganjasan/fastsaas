"""Magic-link tokens — mint and consume single-use, hash-at-rest tokens.

Per ADR-008 §8c and design.md §D3.

Per-purpose TTLs are hardcoded here (single source of truth for the policy).
Raw tokens are 32 bytes of secrets.token_urlsafe; only `sha256(raw)` reaches
the database, so a database leak does not yield usable tokens.

`consume` is designed to run **inside the caller's open transaction** so that
the consumed_at flip and the side effect (e.g. flipping email_verified, updating
the password hash, completing a login) commit or roll back together.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from fastsaas.identity.models import MagicLinkPurpose, MagicLinkToken

PURPOSE_TTL: dict[MagicLinkPurpose, timedelta] = {
    MagicLinkPurpose.MAGIC_LINK_LOGIN: timedelta(minutes=15),
    MagicLinkPurpose.EMAIL_VERIFICATION: timedelta(hours=24),
    MagicLinkPurpose.PASSWORD_RESET: timedelta(hours=1),
    MagicLinkPurpose.ORG_INVITATION: timedelta(days=7),
}

_RAW_TOKEN_BYTES = 32


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


async def mint(
    session: AsyncSession,
    *,
    actor_id: UUID,
    purpose: MagicLinkPurpose,
    email: str,
) -> tuple[str, MagicLinkToken]:
    """Generate a raw token, persist its hash with the right TTL, return (raw, row).

    The raw token is the only place the unhashed value exists; embed it in the
    outbound email URL and discard it.
    """
    raw_token = secrets.token_urlsafe(_RAW_TOKEN_BYTES)
    token = MagicLinkToken(
        token_hash=_hash_token(raw_token),
        purpose=purpose,
        actor_id=actor_id,
        email=email,
        expires_at=datetime.now(UTC) + PURPOSE_TTL[purpose],
    )
    session.add(token)
    await session.flush()
    return raw_token, token


async def consume(
    session: AsyncSession,
    *,
    raw_token: str,
    purpose: MagicLinkPurpose,
) -> MagicLinkToken | None:
    """Atomically mark a single-use token consumed within the caller's transaction.

    Returns the token row (now with consumed_at set) on success.
    Returns None if the token is unknown, of the wrong purpose, expired, or
    already consumed. The caller MUST run its side effect inside the same
    transaction so consume + side effect commit or roll back together.
    """
    now = datetime.now(UTC)
    stmt = (
        update(MagicLinkToken)
        .where(
            MagicLinkToken.token_hash == _hash_token(raw_token),
            MagicLinkToken.purpose == purpose,
            MagicLinkToken.consumed_at.is_(None),
            MagicLinkToken.expires_at > now,
        )
        .values(consumed_at=now)
        .returning(MagicLinkToken)
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return row


async def find_active(
    session: AsyncSession,
    *,
    raw_token: str,
    purpose: MagicLinkPurpose,
) -> MagicLinkToken | None:
    """Lookup-only helper for tests and read paths; does NOT mark consumed."""
    now = datetime.now(UTC)
    stmt = select(MagicLinkToken).where(
        MagicLinkToken.token_hash == _hash_token(raw_token),
        MagicLinkToken.purpose == purpose,
        MagicLinkToken.consumed_at.is_(None),
        MagicLinkToken.expires_at > now,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
