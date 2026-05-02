"""Refresh-token family tracking with rotation and reuse detection.

Per ADR-008 §8a and design.md §D2.

Each login starts a *family* identified by `family_id` (UUID v7). The family's
state lives in a single Redis hash:

    HSET refresh:fam:<family_id>
      current_jti     <jti>
      user_actor_id   <uuid>

Rotation rules — atomic, implemented via a Redis-side Lua script:

- Caller presents a refresh token carrying its `jti`.
- If `current_jti` matches → mint a new `jti`, store it as the new current,
  bump TTL by 30 days (sliding).
- If `current_jti` does NOT match → reuse detected: DEL the family. Subsequent
  refreshes from this family are now `auth.refresh_unknown`.
- If the family does not exist → `auth.refresh_unknown`.

A per-actor index `refresh:actor:<actor_id>` (Redis SET) lets password-reset
revoke all of an actor's families in O(N_families).
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from redis.commands.core import AsyncScript

from fastsaas.cache import get_redis

REFRESH_TTL = timedelta(days=30)
_TTL_SECONDS = int(REFRESH_TTL.total_seconds())


def _family_key(family_id: UUID) -> str:
    return f"refresh:fam:{family_id}"


def _actor_index_key(user_actor_id: UUID) -> str:
    return f"refresh:actor:{user_actor_id}"


class RefreshError(Exception):
    """Base for refresh-rotation failures."""

    code: str = "auth.refresh_invalid"


class RefreshReusedError(RefreshError):
    code = "auth.refresh_reused"


class RefreshUnknownError(RefreshError):
    code = "auth.refresh_unknown"


# Atomic rotate. Returns:
#   1 + new_jti written  → OK
#   0                    → reuse detected (family deleted)
#  -1                    → family not found
_LUA_ROTATE_SOURCE = """
local fam_key = KEYS[1]
local actor_index_key = KEYS[2]
local presented = ARGV[1]
local new_jti = ARGV[2]
local ttl = tonumber(ARGV[3])
local family_id_str = ARGV[4]

local current = redis.call('HGET', fam_key, 'current_jti')
if not current then
  return -1
end
if current ~= presented then
  redis.call('DEL', fam_key)
  redis.call('SREM', actor_index_key, family_id_str)
  return 0
end
redis.call('HSET', fam_key, 'current_jti', new_jti)
redis.call('EXPIRE', fam_key, ttl)
return 1
"""

_rotate_script: AsyncScript | None = None


def _get_rotate_script() -> AsyncScript:
    global _rotate_script
    if _rotate_script is None:
        _rotate_script = get_redis().register_script(_LUA_ROTATE_SOURCE)
    return _rotate_script


def reload_scripts() -> None:
    """Drop the cached Lua script reference. Used by tests that swap the Redis client."""
    global _rotate_script
    _rotate_script = None


async def start_family(user_actor_id: UUID) -> tuple[UUID, UUID]:
    """Create a new refresh family for a user. Returns (family_id, initial_jti)."""
    family_id = uuid4()
    jti = uuid4()
    r = get_redis()
    fam_key = _family_key(family_id)
    actor_key = _actor_index_key(user_actor_id)
    pipe = r.pipeline(transaction=True)
    pipe.hset(fam_key, mapping={"current_jti": str(jti), "user_actor_id": str(user_actor_id)})
    pipe.expire(fam_key, _TTL_SECONDS)
    pipe.sadd(actor_key, str(family_id))
    pipe.expire(actor_key, _TTL_SECONDS)
    await pipe.execute()
    return family_id, jti


async def rotate(family_id: UUID, presented_jti: UUID, user_actor_id: UUID) -> UUID:
    """Atomically rotate a family. Returns the new jti.

    Raises RefreshReusedError on jti mismatch (family is also deleted).
    Raises RefreshUnknownError if the family does not exist.
    """
    new_jti = uuid4()
    script = _get_rotate_script()
    result = await script(
        keys=[_family_key(family_id), _actor_index_key(user_actor_id)],
        args=[str(presented_jti), str(new_jti), _TTL_SECONDS, str(family_id)],
    )
    code = int(result)
    if code == 1:
        return new_jti
    if code == 0:
        raise RefreshReusedError(f"refresh family {family_id} reused; revoked")
    raise RefreshUnknownError(f"refresh family {family_id} not found")


async def revoke_family(family_id: UUID, user_actor_id: UUID) -> None:
    """Logout: delete the family and remove it from the actor index."""
    r = get_redis()
    pipe = r.pipeline(transaction=True)
    pipe.delete(_family_key(family_id))
    pipe.srem(_actor_index_key(user_actor_id), str(family_id))
    await pipe.execute()


async def revoke_all_for_actor(user_actor_id: UUID) -> int:
    """Password reset: delete every family for this actor. Returns the count revoked."""
    r = get_redis()
    actor_key = _actor_index_key(user_actor_id)
    family_ids = await r.smembers(actor_key)
    if not family_ids:
        return 0
    pipe = r.pipeline(transaction=True)
    for fid in family_ids:
        pipe.delete(_family_key(UUID(fid)))
    pipe.delete(actor_key)
    await pipe.execute()
    return len(family_ids)


async def get_current_jti(family_id: UUID) -> UUID | None:
    """Read the current jti for a family (used by tests and the /auth/me debug path)."""
    r = get_redis()
    raw = await r.hget(_family_key(family_id), "current_jti")
    return UUID(raw) if raw else None
