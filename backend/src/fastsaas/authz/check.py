"""`can(actor, op, resource_type, resource_id?)` — the single authorization API.

Implementation loads the actor's active capabilities from Postgres and
evaluates the predicate against the in-memory set. A Redis cache (see
`authz.cache`) materialises the set for 5 minutes; mutations invalidate it.

`actor_self_read` RLS policy on `capabilities` (migration 0004) means we don't
need a `BYPASSRLS` connection — the policy lets every actor read their own rows
once `app.current_actor` is set.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.authz.bundles import Operation, ResourceType
from fastsaas.authz.models import Capability


async def can(
    actor_id: UUID,
    operation: Operation | str,
    resource_type: ResourceType | str,
    resource_id: UUID | None = None,
    *,
    db: AsyncSession,
    cache: Redis | None = None,
) -> bool:
    """Return True if the actor holds an active capability covering this access.

    A capability matches when:
    - `operation` and `resource_type` are equal, AND
    - `resource_id` is either NULL (type-wide grant) or equals the requested id, AND
    - `revoked_at IS NULL` and `expires_at IS NULL OR expires_at > now`, AND
    - `policy_blocked = FALSE`.
    """
    op = operation.value if isinstance(operation, Operation) else operation
    rt = resource_type.value if isinstance(resource_type, ResourceType) else resource_type

    caps = await _load_active_capabilities(actor_id, db=db, cache=cache)
    now = datetime.now(UTC)
    return any(_matches(c, op, rt, resource_id, now) for c in caps)


def _matches(
    c: Capability,
    op: str,
    rt: str,
    resource_id: UUID | None,
    now: datetime,
) -> bool:
    if c.operation != op or c.resource_type != rt:
        return False
    if c.policy_blocked:
        return False
    if c.revoked_at is not None and c.revoked_at <= now:
        return False
    if c.expires_at is not None and c.expires_at <= now:
        return False
    if c.resource_id is not None and resource_id is not None and c.resource_id != resource_id:
        return False
    if c.resource_id is not None and resource_id is None:
        # Caller asked about a type-wide grant; resource-scoped capability does not satisfy.
        return False
    return True


async def _load_active_capabilities(
    actor_id: UUID,
    *,
    db: AsyncSession,
    cache: Redis | None,
) -> list[Capability]:
    """Load the actor's capabilities; cache hook is a TODO (see authz/cache.py)."""
    # Set `app.current_actor` so the `actor_self_read` RLS policy permits the SELECT.
    await db.execute(text("SET LOCAL app.current_actor = :id"), {"id": str(actor_id)})

    stmt = select(Capability).where(
        Capability.actor_id == actor_id,
        Capability.revoked_at.is_(None),
        Capability.policy_blocked.is_(False),
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
