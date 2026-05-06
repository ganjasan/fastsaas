"""Bootstrap CLI — flip `is_platform_staff = TRUE` on a user actor.

Per ADR-019, platform-staff promotion is intentionally a deliberate
out-of-band action. There is no self-service UI: the very first staff
member is bootstrapped via this script run on the deployment host. Staff
promote each other later via the admin UI when that ships.

Usage:
    make seed-platform-staff USER_EMAIL=alice@example.com
    # or directly:
    uv run python -m fastsaas.scripts.seed_platform_staff alice@example.com

The flag flip writes one `audit_log` row (`entity_type="actor"`,
`action="update"`) so the bootstrap itself is auditable. The audit row
records the actor performing the flip as the same target actor — the
bootstrap is by definition self-promoting since no other staff exists
yet to authorise it.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastsaas import audit
from fastsaas.audit.context import IntentContext, set_audit_context
from fastsaas.config import get_settings
from fastsaas.identity.models import Actor, User
from fastsaas.identity.schemas import ActorType, CurrentActor


async def _promote(email: str) -> int:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    try:
        async with factory() as db, db.begin():
            user = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if user is None:
                print(f"[seed-platform-staff] user not found: {email}", file=sys.stderr)
                return 1
            actor = await db.get(Actor, user.actor_id)
            if actor is None:
                print(
                    f"[seed-platform-staff] orphan user row (no actor): {email}",
                    file=sys.stderr,
                )
                return 1
            if actor.is_platform_staff:
                print(f"[seed-platform-staff] {email} is already platform staff — no-op")
                return 0

            await db.execute(
                text(
                    "UPDATE actors SET is_platform_staff = TRUE WHERE id = :id"
                ),
                {"id": str(actor.id)},
            )

            current = CurrentActor(
                actor_id=UUID(str(actor.id)),
                actor_type=ActorType(actor.actor_type),
                parent_actor_id=actor.parent_actor_id,
                email=email,
                email_verified=True,
            )
            with set_audit_context(
                current,
                intent=IntentContext(
                    intent_hash="req:seed-platform-staff",
                    intent_metadata={
                        "source": "seed-platform-staff",
                        "target_email": email,
                    },
                ),
            ):
                await audit.record(
                    db,
                    action="update",
                    entity_type="actor",
                    entity_id=UUID(str(actor.id)),
                    diff={
                        "before": {"is_platform_staff": False},
                        "after": {"is_platform_staff": True},
                    },
                )
            print(f"[seed-platform-staff] promoted {email} to platform staff")
            return 0
    finally:
        await eng.dispose()


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: seed-platform-staff <email>", file=sys.stderr)
        return 2
    return asyncio.run(_promote(argv[0]))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
