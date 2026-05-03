"""Async Redis client factory.

Single connection pool for the process; created lazily on first use, disposed on
app shutdown via lifespan. Used initially by identity/auth/refresh.py for
refresh-family state.
"""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from fastsaas.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = from_url(
            get_settings().redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None
