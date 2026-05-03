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
from fastsaas.api.auth import router as auth_router
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
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
