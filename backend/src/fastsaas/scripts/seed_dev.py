"""Deterministic dev seed.

Loads three verified HUMAN actors (`founder@example.com`,
`member@example.com`, `viewer@example.com`), one organisation
(`acme`), and two projects (`alpha`, `beta`). All seed users share the
same password so a fresh `./run_dev.sh --clean` lets you log in immediately
without registering.

Idempotent: if the founder already exists the script no-ops, so calling
it without `--clean` is harmless.

Usage (typically via `./run_dev.sh --clean`):
    uv run python -m fastsaas.scripts.seed_dev
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fastsaas.config import get_settings
from fastsaas.identity.auth.password import hash_password
from fastsaas.identity.models import Actor, ActorType, User
from fastsaas.tenants.models import OrganisationRole
from fastsaas.tenants.service import (
    MembershipService,
    OrganisationService,
    ProjectService,
)

SEED_PASSWORD = "correct horse battery staple"

# (email, display_name, role) — owner is always first.
SEED_USERS: list[tuple[str, str, OrganisationRole]] = [
    ("founder@example.com", "Founder", OrganisationRole.OWNER),
    ("member@example.com", "Maker", OrganisationRole.MEMBER),
    ("viewer@example.com", "Viewer", OrganisationRole.VIEWER),
]
SEED_ORG_SLUG = "acme"
SEED_ORG_NAME = "Acme Co"
SEED_PROJECTS: list[tuple[str, str]] = [
    ("alpha", "Alpha — onboarding pilot"),
    ("beta", "Beta — internal scratch"),
]


async def _create_actor(db: AsyncSession, *, email: str, display_name: str) -> Actor:
    actor = Actor(actor_type=ActorType.HUMAN, display_name=display_name)
    db.add(actor)
    await db.flush()
    db.add(
        User(
            actor_id=actor.id,
            email=email,
            password_hash=hash_password(SEED_PASSWORD),
            email_verified=True,
        )
    )
    await db.flush()
    return actor


async def seed() -> None:
    settings = get_settings()
    eng = create_async_engine(settings.database_url_migrator, future=True)
    factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)

    try:
        # ── Idempotency check + actor creation ────────────────────────────
        actor_ids: dict[str, str] = {}  # email → actor_id (str-cast for service calls)
        async with factory() as s, s.begin():
            existing = (
                await s.execute(
                    select(Actor)
                    .join(User, User.actor_id == Actor.id)
                    .where(User.email == SEED_USERS[0][0])
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[seed] founder {SEED_USERS[0][0]} already exists — skipping")
                return

            for email, display, _role in SEED_USERS:
                actor = await _create_actor(s, email=email, display_name=display)
                actor_ids[email] = str(actor.id)

            # Dev-only convenience: promote the founder to platform staff so
            # `/admin/*` is reachable out of the box. Production deployments
            # bootstrap via `make seed-platform-staff USER_EMAIL=...` per
            # ADR-019; the dev seed predefines the operator identity, so the
            # equivalent flip happens here without an extra step.
            await s.execute(
                text(
                    "UPDATE actors SET is_platform_staff = TRUE WHERE id = :id"
                ),
                {"id": actor_ids[SEED_USERS[0][0]]},
            )

        # ── Org + projects (owner) ────────────────────────────────────────
        founder_email, _, _ = SEED_USERS[0]
        founder_id = actor_ids[founder_email]

        from uuid import UUID

        org = await OrganisationService.create(
            name=SEED_ORG_NAME,
            slug=SEED_ORG_SLUG,
            owner_actor_id=UUID(founder_id),
        )

        for slug, name in SEED_PROJECTS:
            await ProjectService.create(
                org_id=org.id,
                name=name,
                slug=slug,
                description=None,
                created_by=UUID(founder_id),
            )

        # ── Invite + accept the non-owner members ─────────────────────────
        for email, _display, role in SEED_USERS[1:]:
            raw, _inv = await MembershipService.invite(
                org_id=org.id,
                email=email,
                role=role,
                invited_by=UUID(founder_id),
            )
            await MembershipService.accept(
                raw_token=raw,
                accepting_actor_id=UUID(actor_ids[email]),
            )

        print("[seed] loaded:")
        print(f"  Org:      {org.slug} ({SEED_ORG_NAME})")
        print(f"  Projects: {', '.join(slug for slug, _ in SEED_PROJECTS)}")
        print(f"  Users (password '{SEED_PASSWORD}'):")
        for email, _display, role in SEED_USERS:
            extra = " [PLATFORM STAFF]" if email == SEED_USERS[0][0] else ""
            print(f"    {email:32s} ({role.value}){extra}")
    finally:
        await eng.dispose()


def main() -> int:
    try:
        asyncio.run(seed())
        return 0
    except Exception as exc:
        print(f"[seed] failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
