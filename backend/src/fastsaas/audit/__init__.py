"""Audit log + intent_hash middleware (per ADR-010 + design.md §6).

Public surface:

- `record(...)` — explicit write API for service-layer mutations.
- `AuditedModel` — mixin that opts an ORM class into automatic CRUD audit.
- `AuditContextMiddleware` — populates `actor_var` and `intent_var` per request.
- `actor_var`, `intent_var` — read by `record(...)` and the mapper listeners.
- `IntentContext` — dataclass shape used by `intent_var`.
- `GLOBAL_REDACT`, `redact` — sensitive-field denylist + helper.
- `AuditLog` — SQLModel mirror of `audit_log` for read paths.
"""

from fastsaas.audit.context import (
    IntentContext,
    context_present,
    set_audit_context,
)
from fastsaas.audit.middleware import AuditContextMiddleware
from fastsaas.audit.mixin import AuditedModel
from fastsaas.audit.models import AuditLog
from fastsaas.audit.redact import GLOBAL_REDACT, REDACTED_LITERAL, redact
from fastsaas.audit.service import (
    AuditAction,
    MissingActorError,
    MissingIntentError,
    record,
)

__all__ = [
    "GLOBAL_REDACT",
    "REDACTED_LITERAL",
    "AuditAction",
    "AuditContextMiddleware",
    "AuditLog",
    "AuditedModel",
    "IntentContext",
    "MissingActorError",
    "MissingIntentError",
    "context_present",
    "record",
    "redact",
    "set_audit_context",
]
