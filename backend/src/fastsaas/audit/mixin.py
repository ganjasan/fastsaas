"""`AuditedModel` — Style B from design.md §D2.

Subclasses get free CRUD-level audit rows via SQLAlchemy mapper events.
Used by core entities that don't need bespoke `record(...)` calls AND by
downstream products extending FastSaaS — see ADR-010 amendment.

Soft-delete-flip detection: when only the `deleted_at` column changes from
NULL to a timestamp, the listener emits `action="delete"` rather than
`action="update"`. Restore (NOT NULL → NULL) emits `action="restore"`.

Class attributes the subclass may declare:

- `__audit_entity_type__`: str — open vocabulary, lowercase singular noun
  (default: `__tablename__` minus a trailing `s`).
- `__audit_redact__`: frozenset[str] — extra fields to mask in `diff` on top
  of `GLOBAL_REDACT`.
- `__audit_skip__`: bool — if True, no audit rows are emitted for this
  subclass. Use sparingly; `__audit_skip__ = True` is the right answer for
  caches and scratch tables, never for user-facing data.
"""

from __future__ import annotations

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import event, inspect
from sqlalchemy.orm import Mapper
from sqlmodel import SQLModel

from fastsaas.audit.context import actor_var, intent_var
from fastsaas.audit.service import _record_via_connection

_SOFT_DELETE_COL = "deleted_at"


class AuditedModel(SQLModel):
    """Inherit alongside SQLModel `table=True` to opt a class into automatic
    audit emission for INSERT / UPDATE / DELETE.

    The mixin itself does not declare any DB columns; subclasses define
    their schema as usual. The mapper-event listeners are registered with
    `propagate=True` so every subclass inherits them on import.
    """

    __audit_entity_type__: ClassVar[str | None] = None
    __audit_redact__: ClassVar[frozenset[str]] = frozenset()
    __audit_skip__: ClassVar[bool] = False


def _resolve_entity_type(target: AuditedModel) -> str:
    explicit = getattr(type(target), "__audit_entity_type__", None)
    if explicit:
        return explicit
    table = getattr(type(target), "__tablename__", "")
    return table[:-1] if table.endswith("s") else table


def _column_values(target: AuditedModel) -> dict[str, Any]:
    state = inspect(target)
    return {attr.key: getattr(target, attr.key) for attr in state.mapper.column_attrs}


def _changed_columns(target: AuditedModel) -> dict[str, tuple[Any, Any]]:
    """Map column → (old, new) for every attribute whose history shows a flip."""
    state = inspect(target)
    out: dict[str, tuple[Any, Any]] = {}
    for attr in state.mapper.column_attrs:
        history = state.attrs[attr.key].history
        if not history.has_changes():
            continue
        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else getattr(target, attr.key)
        out[attr.key] = (old, new)
    return out


def _resolve_entity_id(target: AuditedModel) -> UUID | None:
    """Return the row's primary-key UUID if exactly one PK column exists.

    The mixin only supports single-UUID PKs — composite PKs (e.g.
    `organisation_members(organisation_id, actor_id)`) need the explicit
    `record(...)` API.
    """
    pk = inspect(target).mapper.primary_key
    if len(pk) != 1:
        return None
    val = getattr(target, pk[0].key, None)
    if isinstance(val, UUID):
        return val
    return None


def _resolve_org_id(target: AuditedModel) -> UUID | None:
    val = getattr(target, "organisation_id", None)
    return val if isinstance(val, UUID) else None


def _maybe_emit(target: AuditedModel, connection: Any, *, action: str, diff: dict[str, Any]) -> None:
    if getattr(type(target), "__audit_skip__", False):
        return

    actor = actor_var.get()
    intent = intent_var.get()
    if actor is None or intent is None:
        # Outside a request context with no harness having set the contextvars
        # — skip silently. The explicit `record(...)` API is the right tool
        # for offline / migration writes; the mixin is for request-scoped CRUD.
        return

    entity_id = _resolve_entity_id(target)
    if entity_id is None:
        return

    _record_via_connection(
        connection,
        action=action,  # type: ignore[arg-type]
        entity_type=_resolve_entity_type(target),
        entity_id=entity_id,
        diff=diff,
        actor=actor,
        organisation_id=_resolve_org_id(target),
        intent_hash=intent.intent_hash,
        intent_metadata=intent.intent_metadata,
        extra_redact=type(target).__audit_redact__,
    )


# SQLModel only maps `table=True` subclasses, so `AuditedModel` itself has no
# Mapper and `event.listens_for(AuditedModel, ..., propagate=True)` would be a
# silent no-op. Listening on `Mapper` globally and filtering by `isinstance`
# fires reliably for every concrete subclass — including downstream domain
# classes defined outside this repo.


@event.listens_for(Mapper, "after_insert")
def _on_insert(_mapper: Any, connection: Any, target: Any) -> None:
    if not isinstance(target, AuditedModel):
        return
    diff = {"before": {}, "after": _column_values(target)}
    _maybe_emit(target, connection, action="create", diff=diff)


@event.listens_for(Mapper, "after_update")
def _on_update(_mapper: Any, connection: Any, target: Any) -> None:
    if not isinstance(target, AuditedModel):
        return
    changed = _changed_columns(target)
    if not changed:
        return  # SQLAlchemy can fire on no-op flushes
    before = {k: old for k, (old, _new) in changed.items()}
    after = {k: new for k, (_old, new) in changed.items()}

    if list(changed.keys()) == [_SOFT_DELETE_COL]:
        old, new = changed[_SOFT_DELETE_COL]
        if old is None and new is not None:
            action = "delete"
        elif old is not None and new is None:
            action = "restore"
        else:
            action = "update"
    else:
        action = "update"

    _maybe_emit(target, connection, action=action, diff={"before": before, "after": after})


@event.listens_for(Mapper, "after_delete")
def _on_delete(_mapper: Any, connection: Any, target: Any) -> None:
    if not isinstance(target, AuditedModel):
        return
    diff = {"before": _column_values(target), "after": {}}
    _maybe_emit(target, connection, action="delete", diff=diff)
