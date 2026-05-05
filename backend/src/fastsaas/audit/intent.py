"""`compute_intent_hash` — deterministic source-prefixed fingerprint per request.

Per ADR-010 amendment (and spike `platform-saas-core-architecture-spike`
Decision #6) every audit row carries an `intent_hash` whose prefix names the
source. The four sources, in priority order:

1. `agent:<sha256>` — `X-Agent-Intent` header (free-form prompt). Lets the
   compliance officer group every audit row produced by one AGENT prompt.
2. `idem:<sha256>` — `Idempotency-Key` header. Lets repeated retries of the
   same logical action collapse to one provable trail.
3. `sess:<sha256>` — `X-Session-Intent` header (multi-step UI flow). The
   frontend stamps it once at the top of a wizard and every step shares
   the prefix.
4. `req:<request_id>` — fallback. Each request gets its own group; this
   is the common case for one-shot HUMAN actions.

Hashes are sha256-truncated to 16 hex chars (8 bytes / 64 bits) — enough to
make accidental collisions vanishingly rare across a single org's audit
window without ballooning the column.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import Request

_HASH_LEN = 16  # hex chars

# Cap client-controlled string fields before they reach immortal `audit_log`
# storage. Keeps an authenticated attacker from writing arbitrarily large
# `X-Agent-Intent` / `X-Request-ID` / `User-Agent` headers into every row
# they generate. uvicorn's default total-header limit (~8KB) is deployment-
# dependent; this is the in-app backstop that survives deployment drift.
_MAX_FIELD_LEN = 4096


def _short(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:_HASH_LEN]


def _bounded(value: str | None) -> str | None:
    if value is None:
        return None
    return value[:_MAX_FIELD_LEN]


def compute_intent_hash(request: Request) -> tuple[str, dict[str, Any]]:
    """Resolve `(intent_hash, intent_metadata)` for the request.

    Header precedence is `agent:` > `idem:` > `sess:` > `req:`.
    `intent_metadata` always carries `request_id`, `path`, `method`, and
    best-effort `ip` + `user_agent`. AGENT-initiated requests also carry
    the raw `original_prompt` for forensic replay (subject to redaction
    if downstreams want to suppress it).
    """
    headers = request.headers
    request_id = _bounded(headers.get("x-request-id")) or uuid.uuid4().hex

    metadata: dict[str, Any] = {
        "request_id": request_id,
        "path": str(request.url.path),
        "method": request.method,
    }
    ua = _bounded(headers.get("user-agent"))
    if ua:
        metadata["user_agent"] = ua
    if request.client is not None:
        metadata["ip"] = request.client.host

    agent_intent = _bounded(headers.get("x-agent-intent"))
    if agent_intent:
        metadata["original_prompt"] = agent_intent
        return f"agent:{_short(agent_intent)}", metadata

    idem_key = headers.get("idempotency-key")
    if idem_key:
        return f"idem:{_short(idem_key)}", metadata

    sess_intent = headers.get("x-session-intent")
    if sess_intent:
        return f"sess:{_short(sess_intent)}", metadata

    return f"req:{request_id}", metadata
