"""FastAPI app entry point.

Bootstrap scope (#1) ships `/health` plus the identity layer (#2). Tenants
(#3), audit (#4), design system (#5), observability (#6), and e2e (#7) land
in their respective issues.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from fastsaas import __version__
from fastsaas.api.audit import router as audit_router
from fastsaas.api.auth import router as auth_router
from fastsaas.api.orgs import router as orgs_router
from fastsaas.api.projects import (
    accept_share_router as projects_accept_share_router,
)
from fastsaas.api.projects import (
    router as projects_router,
)
from fastsaas.audit import AuditContextMiddleware
from fastsaas.cache import close_redis, get_redis
from fastsaas.config import get_settings
from fastsaas.db import close_engine, session_scope


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Startup probes: DB and Redis must be reachable before the app declares ready.
    async with session_scope() as session:
        await session.execute(text("SELECT 1"))
    await get_redis().ping()
    yield
    await close_redis()
    await close_engine()


app = FastAPI(title=get_settings().app_name, version=__version__, lifespan=lifespan)

# Audit context middleware sets `actor_var` and `intent_var` for every
# request so service-layer `record(...)` calls and `AuditedModel` mapper
# events have an actor + intent to attach to the audit row.
app.add_middleware(AuditContextMiddleware)

app.include_router(auth_router)
app.include_router(orgs_router)
app.include_router(projects_router)
app.include_router(projects_accept_share_router)
app.include_router(audit_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
