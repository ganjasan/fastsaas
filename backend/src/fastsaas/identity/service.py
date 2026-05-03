"""Use-case orchestration for identity flows.

Routes call into this module; this module composes ORM, password, JWT, refresh,
magic_link, email, and OAuth primitives. Service-level errors carry a `code`
that the route layer maps to an HTTP status; this keeps handlers thin.

Each flow that mints tokens returns `(access_token, refresh_token, family_id, actor)`
so the caller can set the refresh cookie + access body in a single place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

import uuid_utils
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from fastsaas.identity.auth import jwt as jwt_module
from fastsaas.identity.auth import magic_link as magic_link_module
from fastsaas.identity.auth import password as password_module
from fastsaas.identity.auth import refresh as refresh_module
from fastsaas.identity.auth.oauth import OAuthIdentityClaims
from fastsaas.identity.models import (
    Actor,
    ActorType,
    MagicLinkPurpose,
    OAuthIdentity,
    User,
)

logger = logging.getLogger(__name__)


def _new_actor_uuid() -> UUID:
    """uuid_utils.uuid7 returns its own UUID class; coerce to stdlib UUID for Pydantic strict typing."""
    return UUID(str(uuid_utils.uuid7()))


class AuthServiceError(Exception):
    """Base for service-level identity failures. Has `code` + `status_code`."""

    code: str = "auth.error"
    status_code: int = 400


class EmailTakenError(AuthServiceError):
    code = "auth.email_taken"
    status_code = 409


class PasswordTooShortServiceError(AuthServiceError):
    code = "auth.password_too_short"
    status_code = 400


class InvalidCredentialsError(AuthServiceError):
    code = "auth.invalid_credentials"
    status_code = 401


class EmailUnverifiedError(AuthServiceError):
    code = "auth.email_unverified"
    status_code = 403


class AccountDisabledError(AuthServiceError):
    code = "auth.account_disabled"
    status_code = 401


class TokenInvalidServiceError(AuthServiceError):
    code = "auth.token_invalid"
    status_code = 400


class TokenExpiredServiceError(AuthServiceError):
    code = "auth.token_expired"
    status_code = 410


class TokenConsumedError(AuthServiceError):
    code = "auth.token_consumed"
    status_code = 410


class RefreshReusedApiError(AuthServiceError):
    code = "auth.refresh_reused"
    status_code = 401


class RefreshUnknownApiError(AuthServiceError):
    code = "auth.refresh_unknown"
    status_code = 401


class OAuthEmailTakenError(AuthServiceError):
    code = "auth.oauth_email_taken"
    status_code = 409


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    family_id: UUID
    actor: Actor


async def _find_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()


async def _load_actor(session: AsyncSession, actor_id: UUID) -> Actor | None:
    return await session.get(Actor, actor_id)


async def _issue_tokens(actor: Actor) -> IssuedTokens:
    family_id, jti = await refresh_module.start_family(actor.id)
    access = jwt_module.encode_access(actor, family_id)
    refresh = jwt_module.encode_refresh(family_id, jti, actor.id)
    return IssuedTokens(
        access_token=access, refresh_token=refresh, family_id=family_id, actor=actor
    )


async def register_user(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
) -> tuple[Actor, str]:
    """Create a HUMAN actor + user. Returns `(actor, verification_raw_token)`.

    Caller is responsible for committing the transaction and dispatching the
    verification email post-commit (email is an external side effect that
    must not happen if the commit fails).

    Raises `PasswordTooShortServiceError` for short passwords; `EmailTakenError` for duplicate emails.
    """
    try:
        password_hash = password_module.hash_password(password)
    except password_module.PasswordTooShortError as e:
        raise PasswordTooShortServiceError(str(e)) from e

    actor = Actor(
        id=_new_actor_uuid(),
        actor_type=ActorType.HUMAN,
        display_name=display_name or email.split("@", 1)[0],
        parent_actor_id=None,
    )
    session.add(actor)
    try:
        await session.flush()
    except IntegrityError as e:
        raise EmailTakenError(str(e)) from e
    user = User(actor_id=actor.id, email=email, password_hash=password_hash)
    session.add(user)
    try:
        await session.flush()
    except IntegrityError as e:
        raise EmailTakenError(str(e)) from e

    raw_token, _ = await magic_link_module.mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.EMAIL_VERIFICATION,
        email=email,
    )
    return actor, raw_token


async def verify_email(session: AsyncSession, *, raw_token: str) -> User:
    """Consume an email-verification magic-link and flip `users.email_verified = TRUE`.

    Raises `TokenInvalidServiceError` (unknown / wrong purpose / expired / consumed).
    """
    consumed = await magic_link_module.consume(
        session, raw_token=raw_token, purpose=MagicLinkPurpose.EMAIL_VERIFICATION
    )
    if consumed is None:
        raise TokenInvalidServiceError("email verification token rejected")
    user = (
        await session.execute(select(User).where(User.actor_id == consumed.actor_id))
    ).scalar_one()
    user.email_verified = True
    session.add(user)
    await session.flush()
    return user


async def login_with_password(
    session: AsyncSession, *, email: str, password: str
) -> IssuedTokens:
    """Verify credentials + email_verified + not deleted → mint tokens."""
    user = await _find_user_by_email(session, email)
    if user is None or user.password_hash is None:
        raise InvalidCredentialsError("no such user / no password set")
    if not password_module.verify_password(password, user.password_hash):
        raise InvalidCredentialsError("password mismatch")
    actor = await _load_actor(session, user.actor_id)
    if actor is None or actor.deleted_at is not None:
        raise AccountDisabledError("actor disabled")
    if not user.email_verified:
        raise EmailUnverifiedError("email not verified")
    return await _issue_tokens(actor)


async def login_with_magic_link(
    session: AsyncSession, *, raw_token: str
) -> IssuedTokens:
    """Consume a magic-link login token, mint tokens. Implicit email verification on success."""
    consumed = await magic_link_module.consume(
        session, raw_token=raw_token, purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN
    )
    if consumed is None:
        raise TokenInvalidServiceError("magic-link token rejected")
    actor = await _load_actor(session, consumed.actor_id)
    if actor is None or actor.deleted_at is not None:
        raise AccountDisabledError("actor disabled")
    user = (
        await session.execute(select(User).where(User.actor_id == actor.id))
    ).scalar_one()
    if not user.email_verified:
        # Magic-link login also verifies the address — the user proved control of it.
        user.email_verified = True
        session.add(user)
        await session.flush()
    return await _issue_tokens(actor)


async def request_magic_link(session: AsyncSession, *, email: str) -> str | None:
    """Mint a magic-link login token. Returns the raw token (caller emails post-commit) or None.

    Returns None if the email matches no user / a soft-deleted actor — callers
    SHOULD still respond with HTTP 202 to prevent account enumeration.
    """
    user = await _find_user_by_email(session, email)
    if user is None:
        return None
    actor = await _load_actor(session, user.actor_id)
    if actor is None or actor.deleted_at is not None:
        return None
    raw_token, _ = await magic_link_module.mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.MAGIC_LINK_LOGIN,
        email=email,
    )
    return raw_token


async def request_password_reset(session: AsyncSession, *, email: str) -> str | None:
    """Mint a password-reset token. Returns the raw token (caller emails post-commit) or None.

    None on no-such-user / disabled — caller still returns HTTP 202.
    """
    user = await _find_user_by_email(session, email)
    if user is None:
        return None
    actor = await _load_actor(session, user.actor_id)
    if actor is None or actor.deleted_at is not None:
        return None
    raw_token, _ = await magic_link_module.mint(
        session,
        actor_id=actor.id,
        purpose=MagicLinkPurpose.PASSWORD_RESET,
        email=email,
    )
    return raw_token


async def complete_password_reset(
    session: AsyncSession, *, raw_token: str, new_password: str
) -> User:
    """Consume the reset token, hash the new password, revoke all refresh families for this actor."""
    try:
        new_hash = password_module.hash_password(new_password)
    except password_module.PasswordTooShortError as e:
        raise PasswordTooShortServiceError(str(e)) from e

    consumed = await magic_link_module.consume(
        session, raw_token=raw_token, purpose=MagicLinkPurpose.PASSWORD_RESET
    )
    if consumed is None:
        raise TokenInvalidServiceError("password-reset token rejected")
    user = (
        await session.execute(select(User).where(User.actor_id == consumed.actor_id))
    ).scalar_one()
    user.password_hash = new_hash
    session.add(user)
    await session.flush()
    await refresh_module.revoke_all_for_actor(consumed.actor_id)
    return user


async def refresh_session(session: AsyncSession, *, refresh_token: str) -> IssuedTokens:
    """Verify the refresh JWT, rotate via Redis, mint a new pair."""
    try:
        claims = jwt_module.decode_refresh(refresh_token)
    except jwt_module.TokenExpiredError as e:
        raise TokenExpiredServiceError(str(e)) from e
    except jwt_module.TokenError as e:
        raise TokenInvalidServiceError(str(e)) from e
    family_id = UUID(claims["family_id"])
    presented_jti = UUID(claims["jti"])
    user_actor_id = UUID(claims["sub"])
    try:
        new_jti = await refresh_module.rotate(family_id, presented_jti, user_actor_id)
    except refresh_module.RefreshReusedError as e:
        raise RefreshReusedApiError(str(e)) from e
    except refresh_module.RefreshUnknownError as e:
        raise RefreshUnknownApiError(str(e)) from e
    actor = await _load_actor(session, user_actor_id)
    if actor is None or actor.deleted_at is not None:
        raise AccountDisabledError("actor disabled")
    new_access = jwt_module.encode_access(actor, family_id)
    new_refresh = jwt_module.encode_refresh(family_id, new_jti, actor.id)
    return IssuedTokens(
        access_token=new_access,
        refresh_token=new_refresh,
        family_id=family_id,
        actor=actor,
    )


async def logout(refresh_token: str) -> None:
    """Decode the refresh JWT and revoke its family. Best-effort: malformed cookies are ignored."""
    try:
        claims = jwt_module.decode_refresh(refresh_token)
    except jwt_module.TokenError:
        return
    family_id = UUID(claims["family_id"])
    user_actor_id = UUID(claims["sub"])
    await refresh_module.revoke_family(family_id, user_actor_id)


async def complete_oauth(
    session: AsyncSession, *, claims: OAuthIdentityClaims
) -> IssuedTokens:
    """Branch logic for OAuth callback per auth-flows §"OAuth login".

    - existing oauth_identities → log in linked user
    - email matches a User but no oauth_identities → 409 oauth_email_taken
    - new email + new oauth_identities → create actor + user (email_verified=TRUE)
    """
    existing = (
        await session.execute(
            select(OAuthIdentity).where(
                OAuthIdentity.provider == claims.provider,
                OAuthIdentity.provider_uid == claims.provider_uid,
            )
        )
    ).scalar_one_or_none()

    if existing:
        actor = await _load_actor(session, existing.user_actor_id)
        if actor is None or actor.deleted_at is not None:
            raise AccountDisabledError("linked actor disabled")
        return await _issue_tokens(actor)

    user_by_email = await _find_user_by_email(session, claims.email)
    if user_by_email:
        raise OAuthEmailTakenError(
            "email exists with password login; sign in and link OAuth from settings"
        )

    actor = Actor(
        id=_new_actor_uuid(),
        actor_type=ActorType.HUMAN,
        display_name=claims.email.split("@", 1)[0],
        parent_actor_id=None,
    )
    session.add(actor)
    await session.flush()
    user = User(
        actor_id=actor.id,
        email=claims.email,
        email_verified=True,  # OAuth provider attests
    )
    session.add(user)
    # Flush user before identity: oauth_identities.user_actor_id FKs to users.actor_id
    # and SQLAlchemy doesn't auto-order independent inserts.
    await session.flush()
    identity = OAuthIdentity(
        provider=claims.provider,
        provider_uid=claims.provider_uid,
        user_actor_id=actor.id,
    )
    session.add(identity)
    await session.flush()
    return await _issue_tokens(actor)
