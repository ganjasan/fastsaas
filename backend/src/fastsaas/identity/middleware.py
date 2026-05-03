"""FastAPI dependencies — current_actor + composable guards.

`current_actor` reads `Authorization: Bearer <jwt>`, verifies the access token,
loads the joined Actor+User row, and returns a typed `CurrentActor`. Routes
that need extra constraints layer `require_human` / `require_verified_email`
on top.

Per actor-identity §"current_actor dependency":
- missing token → HTTP 401 `auth.token_missing`
- expired       → HTTP 401 `auth.token_expired`
- bad token     → HTTP 401 `auth.token_invalid`
- soft-deleted  → HTTP 401 `auth.account_disabled`
- unverified email (when guard active) → HTTP 403 `auth.email_unverified`
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from fastsaas.db import session_scope
from fastsaas.identity.auth import jwt as jwt_module
from fastsaas.identity.models import Actor, ActorType, User
from fastsaas.identity.schemas import CurrentActor


def _raise(code: str, status_code: int, message: str) -> None:
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


async def get_session() -> AsyncSession:  # pragma: no cover - thin wrapper
    """Per-request DB session dependency. Wraps `session_scope` so handlers can `Depends(get_session)`."""
    async with session_scope() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def current_actor(request: Request, session: SessionDep) -> CurrentActor:
    """Resolve the calling actor from the bearer access token. Raises HTTPException on failure."""
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        _raise("auth.token_missing", status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = auth_header.split(" ", 1)[1].strip()
    try:
        claims = jwt_module.decode_access(token)
    except jwt_module.TokenExpiredError:
        _raise("auth.token_expired", status.HTTP_401_UNAUTHORIZED, "access token expired")
    except jwt_module.TokenWrongTypeError:
        _raise("auth.token_invalid", status.HTTP_401_UNAUTHORIZED, "wrong token type")
    except jwt_module.TokenError:
        _raise("auth.token_invalid", status.HTTP_401_UNAUTHORIZED, "invalid token")

    actor_id = UUID(claims["sub"])
    actor = await session.get(Actor, actor_id)
    if actor is None or actor.deleted_at is not None:
        _raise("auth.account_disabled", status.HTTP_401_UNAUTHORIZED, "actor disabled")
    user = (
        await session.execute(select(User).where(User.actor_id == actor_id))
    ).scalar_one_or_none()
    if user is None:
        _raise("auth.account_disabled", status.HTTP_401_UNAUTHORIZED, "user row missing")

    return CurrentActor(
        actor_id=actor.id,
        actor_type=actor.actor_type,
        parent_actor_id=actor.parent_actor_id,
        email=user.email,
        email_verified=user.email_verified,
    )


CurrentActorDep = Annotated[CurrentActor, Depends(current_actor)]


def require_human(actor: CurrentActorDep) -> CurrentActor:
    """Reject non-HUMAN actors at 403."""
    if actor.actor_type is not ActorType.HUMAN:
        _raise(
            "auth.actor_type_forbidden",
            status.HTTP_403_FORBIDDEN,
            "this endpoint is for human actors only",
        )
    return actor


HumanActorDep = Annotated[CurrentActor, Depends(require_human)]


def require_verified_email(actor: CurrentActorDep) -> CurrentActor:
    """Reject actors whose email isn't verified at 403."""
    if not actor.email_verified:
        _raise(
            "auth.email_unverified",
            status.HTTP_403_FORBIDDEN,
            "email address not verified",
        )
    return actor


VerifiedEmailActorDep = Annotated[CurrentActor, Depends(require_verified_email)]
