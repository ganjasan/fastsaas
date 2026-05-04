"""Sensitive-field redaction for audit diffs.

Per ADR-010 amendment, redaction is layered:

- `GLOBAL_REDACT` — fields never written into `audit_log.diff` regardless
  of which entity they came from. New PRs that introduce sensitive fields
  MUST extend this set.
- Per-model `__audit_redact__` — declared on `AuditedModel` subclasses;
  merged with the global set, never replaces it.
- Per-call `extra_redact=` — passed to `record(...)` for one-off keys.

Redacted fields appear in the stored diff with the literal string
`"<redacted>"` rather than being dropped — presence-of-key remains
observable so the compliance officer can tell that a sensitive field
existed on this revision without leaking the value itself.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

GLOBAL_REDACT: frozenset[str] = frozenset(
    {
        "password_hash",
        "token_hash",
        "api_key_hash",
        "key_hash",
        "client_secret",
        "raw_token",
    }
)

REDACTED_LITERAL = "<redacted>"


def _redact_side(side: dict[str, Any], deny: frozenset[str]) -> dict[str, Any]:
    return {k: (REDACTED_LITERAL if k in deny else v) for k, v in side.items()}


def redact(
    diff: dict[str, Any], *, extra: Iterable[str] | None = None
) -> dict[str, Any]:
    """Return a new diff with `before` / `after` sensitive keys masked.

    The shape `{"before": {...}, "after": {...}}` is preserved; missing
    sides default to `{}` so callers don't have to construct empty dicts.
    Non-string keys in either side are kept untouched (the denylist is
    string-only and Python dict keys for an ORM diff are always strings).
    """
    deny = GLOBAL_REDACT if extra is None else GLOBAL_REDACT | frozenset(extra)
    before = diff.get("before") or {}
    after = diff.get("after") or {}
    return {
        "before": _redact_side(before, deny),
        "after": _redact_side(after, deny),
    }
