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


def _redact_value(value: Any, deny: frozenset[str]) -> Any:
    """Recursively mask denied keys inside dicts and lists.

    ORM column-level diffs are flat, but explicit `record(...)` callers
    can pass nested structures (e.g. settings updates with a nested
    `oauth.client_secret`). Walking only the top level would leak secrets
    that happen to live one level deep. Lists are traversed so a list of
    dicts (e.g. config snapshots) is also covered.
    """
    if isinstance(value, dict):
        return {
            k: (REDACTED_LITERAL if k in deny else _redact_value(v, deny))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, deny) for item in value]
    return value


def redact(
    diff: dict[str, Any], *, extra: Iterable[str] | None = None
) -> dict[str, Any]:
    """Return a new diff with `before` / `after` sensitive keys masked
    recursively at any depth.

    The shape `{"before": {...}, "after": {...}}` is preserved; missing
    sides default to `{}` so callers don't have to construct empty dicts.
    """
    deny = GLOBAL_REDACT if extra is None else GLOBAL_REDACT | frozenset(extra)
    return {
        "before": _redact_value(diff.get("before") or {}, deny),
        "after": _redact_value(diff.get("after") or {}, deny),
    }
