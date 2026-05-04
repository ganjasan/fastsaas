"""Per-request actor + intent context for audit writes.

Two contextvars carry the audit-relevant request state through every awaited
service-layer call without threading them through every signature:

- `actor_var` — the resolved `CurrentActor`, or `None` for unauthenticated /
  pre-auth segments (e.g. `POST /auth/login`).
- `intent_var` — the `IntentContext` carrying `intent_hash` (prefixed source
  per ADR-010 amendment + spike Decision #6) and free-form `intent_metadata`.

The middleware (`AuditContextMiddleware`) sets both at request entry and
resets at exit. `asyncio.TaskGroup` and ordinary `await` propagate
contextvars correctly; FastAPI `BackgroundTasks` inherits them at enqueue
time. Workers (future arq epic) MUST set `actor_var` from the serialised
job context — that contract is documented in ADR-010 §"Actor + intent flow".
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from fastsaas.identity.schemas import CurrentActor


@dataclass(frozen=True, slots=True)
class IntentContext:
    """A request's intent fingerprint plus free-form metadata.

    `intent_hash` is the prefixed source per ADR-010 amendment:
    `idem:<sha>` (Idempotency-Key header), `agent:<sha>` (X-Agent-Intent
    header), `sess:<sha>` (multi-step session intent), or `req:<id>` (default
    per-request).
    `intent_metadata` is whatever the middleware decided was useful — IP,
    user-agent, request path, original prompt for AGENT actors, etc.
    """

    intent_hash: str
    intent_metadata: dict[str, Any] = field(default_factory=dict)


actor_var: ContextVar[CurrentActor | None] = ContextVar("audit.actor", default=None)
intent_var: ContextVar[IntentContext | None] = ContextVar("audit.intent", default=None)


@contextmanager
def set_audit_context(
    actor: CurrentActor, *, intent: IntentContext | None = None
) -> Iterator[None]:
    """Manually pin actor + intent for the current task — for tests, scripts,
    and worker harnesses. HTTP requests get this for free via
    `AuditContextMiddleware`. The default `intent` is a synthetic
    `req:test` placeholder so tests don't have to construct one when they
    don't care about the source-prefix detail."""
    atok = actor_var.set(actor)
    itok = intent_var.set(intent or IntentContext(intent_hash="req:test"))
    try:
        yield
    finally:
        actor_var.reset(atok)
        intent_var.reset(itok)
