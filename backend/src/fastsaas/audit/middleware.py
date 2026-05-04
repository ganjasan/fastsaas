"""`AuditContextMiddleware` — sets `actor_var` + `intent_var` per request.

Wired in `main.py`. The middleware does a best-effort JWT decode to populate
`actor_var`; it never raises on missing / expired tokens because the
authoritative auth check is the route-level `current_actor` dependency.
Endpoints that don't require auth (e.g. `/auth/login`) simply run with
`actor_var = None`, and `record(...)` will refuse to write — those routes
must pass `actor=` explicitly when they audit anything.

`intent_var` is always populated; `compute_intent_hash` falls back to a
generated `req:<uuid>` when no source headers are present.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlmodel import select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from fastsaas.audit.context import IntentContext, actor_var, intent_var
from fastsaas.audit.intent import compute_intent_hash
from fastsaas.db import migrator_session_scope
from fastsaas.identity.auth import jwt as jwt_module
from fastsaas.identity.models import Actor, User
from fastsaas.identity.schemas import CurrentActor

log = logging.getLogger(__name__)


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next
    ) -> Response:
        intent_hash, intent_metadata = compute_intent_hash(request)
        actor = await _maybe_resolve_actor(request)

        atok = actor_var.set(actor)
        itok = intent_var.set(IntentContext(intent_hash, intent_metadata))
        try:
            return await call_next(request)
        finally:
            actor_var.reset(atok)
            intent_var.reset(itok)


async def _maybe_resolve_actor(request: Request) -> CurrentActor | None:
    """Decode `Authorization: Bearer <jwt>` best-effort.

    Returns `None` for any of: missing header, malformed prefix, decode
    failure, expired/wrong-type token, deleted actor, missing user row.
    Hard auth checks remain the route's `current_actor` dependency — this
    is purely to populate `actor_var` for the request's audit writes.
    """
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()

    try:
        claims = jwt_module.decode_access(token)
    except jwt_module.TokenError:
        return None

    try:
        actor_id = UUID(claims["sub"])
    except (KeyError, ValueError):
        return None

    try:
        async with migrator_session_scope() as db:
            actor = await db.get(Actor, actor_id)
            if actor is None or actor.deleted_at is not None:
                return None
            user = (
                await db.execute(select(User).where(User.actor_id == actor_id))
            ).scalar_one_or_none()
            if user is None:
                return None
            return CurrentActor(
                actor_id=actor.id,
                actor_type=actor.actor_type,
                parent_actor_id=actor.parent_actor_id,
                email=user.email,
                email_verified=user.email_verified,
            )
    except Exception:
        log.warning("audit middleware: best-effort actor resolution failed", exc_info=True)
        return None


def install(app: ASGIApp) -> None:
    """Helper for `main.py` so the wiring stays a one-liner."""
    app.add_middleware(AuditContextMiddleware)  # type: ignore[attr-defined]
