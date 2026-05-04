"""`AuditContextMiddleware` — sets `intent_var` per request.

`actor_var` is set by the `current_actor` FastAPI dependency once it has
already decoded the bearer token and loaded the actor row — that avoids
a second DB round-trip per request just to populate audit context.
Endpoints without `current_actor` (e.g. `/auth/login`) run with
`actor_var = None`, and `record(...)` refuses to write — those routes
pass `actor=` explicitly when they audit anything.

`intent_var` is always populated; `compute_intent_hash` falls back to a
generated `req:<uuid>` when no source headers are present.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fastsaas.audit.context import IntentContext, intent_var
from fastsaas.audit.intent import compute_intent_hash


class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(  # type: ignore[override]
        self, request: Request, call_next
    ) -> Response:
        intent_hash, intent_metadata = compute_intent_hash(request)
        token = intent_var.set(IntentContext(intent_hash, intent_metadata))
        try:
            return await call_next(request)
        finally:
            intent_var.reset(token)
