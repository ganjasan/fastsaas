"""Explicit `record(...)` write API — Style A from design.md §D2.

Service-layer mutations call `await audit.record(db, ...)` inside their open
transaction. Defaults `actor`, `intent_hash`, and `intent_metadata` come from
the request contextvars set by `AuditContextMiddleware`. The redaction step
runs on `diff` before insert per ADR-010 amendment.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.audit.context import IntentContext, actor_var, intent_var
from fastsaas.audit.models import AuditLog
from fastsaas.audit.redact import redact
from fastsaas.identity.schemas import CurrentActor

AuditAction = Literal["create", "update", "delete", "restore"]


class MissingActorError(RuntimeError):
    """Raised when `record(...)` is called outside a request context and no
    `actor=` is passed. Audit rows REQUIRE a non-null actor (FK to actors.id);
    silently dropping the write would create a coverage gap. The fix is
    either to set `actor_var` from a worker harness or to pass `actor=`
    explicitly at the call site."""


class MissingIntentError(RuntimeError):
    """Raised when `record(...)` is called without `intent_var` set and no
    `intent_hash=` is passed. The audit contract pins `intent_hash` as
    NOT NULL — see `AuditContextMiddleware`."""


async def record(
    db: AsyncSession,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: UUID,
    diff: dict[str, Any],
    actor: CurrentActor | None = None,
    organisation_id: UUID | None = None,
    intent_hash: str | None = None,
    intent_metadata: dict[str, Any] | None = None,
    extra_intent_metadata: dict[str, Any] | None = None,
    extra_redact: Iterable[str] | None = None,
) -> AuditLog:
    """Append one row to `audit_log` inside the caller's open transaction.

    `actor`, `intent_hash`, and `intent_metadata` default to the request
    contextvars (`actor_var`, `intent_var`). `extra_intent_metadata` is
    merged onto whatever the middleware computed — e.g. the org-create
    service stamps `{"org_id": str(org.id)}` so the row is queryable by
    org even though `organisation_id` is the FK column.

    The redaction step runs over `diff` before insert. Pass `extra_redact`
    for one-off sensitive keys not in `GLOBAL_REDACT`.
    """
    resolved_actor = actor if actor is not None else actor_var.get()
    if resolved_actor is None:
        raise MissingActorError(
            f"record({entity_type}/{action}) called without actor "
            "and actor_var is unset; set actor= explicitly"
        )

    if intent_hash is None or intent_metadata is None:
        intent: IntentContext | None = intent_var.get()
        if intent is None and (intent_hash is None or intent_metadata is None):
            raise MissingIntentError(
                f"record({entity_type}/{action}) called without intent_hash "
                "and intent_var is unset; set intent_hash= explicitly"
            )
        if intent_hash is None:
            assert intent is not None  # for type-checker
            intent_hash = intent.intent_hash
        if intent_metadata is None:
            intent_metadata = dict(intent.intent_metadata) if intent is not None else {}

    if extra_intent_metadata:
        intent_metadata = {**intent_metadata, **extra_intent_metadata}

    redacted_diff = redact(diff, extra=extra_redact)

    row = AuditLog(
        actor_id=resolved_actor.actor_id,
        actor_type=str(resolved_actor.actor_type),
        parent_actor_id=resolved_actor.parent_actor_id,
        organisation_id=organisation_id,
        intent_hash=intent_hash,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        diff=redacted_diff,
        intent_metadata=intent_metadata,
    )
    db.add(row)
    await db.flush()
    return row


def record_via_connection(
    connection: Any,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: UUID,
    diff: dict[str, Any],
    actor: CurrentActor,
    organisation_id: UUID | None,
    intent_hash: str,
    intent_metadata: dict[str, Any],
    extra_redact: Iterable[str] | None = None,
) -> None:
    """Synchronous INSERT used by mapper-event listeners.

    Mapper events fire synchronously inside the flush. Even on an async
    engine, the callback runs in the greenlet adapter — the `connection`
    argument is a sync `Connection` (or its greenlet-wrapped equivalent),
    and `connection.execute(...)` is a plain blocking call. Defining this
    helper as `async def` would make the call site `await`-needing, which
    the sync event hook can't do — the result was a never-awaited coroutine
    and zero audit rows.
    """
    redacted_diff = redact(diff, extra=extra_redact)
    connection.execute(
        text(
            "INSERT INTO audit_log "
            "(actor_id, actor_type, parent_actor_id, organisation_id, "
            "intent_hash, entity_type, entity_id, action, diff, intent_metadata) "
            "VALUES (:actor_id, :actor_type, :parent_actor_id, :organisation_id, "
            ":intent_hash, :entity_type, :entity_id, :action, "
            "CAST(:diff AS jsonb), CAST(:intent_metadata AS jsonb))"
        ),
        {
            "actor_id": str(actor.actor_id),
            "actor_type": str(actor.actor_type),
            "parent_actor_id": (
                str(actor.parent_actor_id) if actor.parent_actor_id else None
            ),
            "organisation_id": (
                str(organisation_id) if organisation_id is not None else None
            ),
            "intent_hash": intent_hash,
            "entity_type": entity_type,
            "entity_id": str(entity_id),
            "action": action,
            "diff": _json_dump(redacted_diff),
            "intent_metadata": _json_dump(intent_metadata),
        },
    )


def _json_dump(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, default=str)
