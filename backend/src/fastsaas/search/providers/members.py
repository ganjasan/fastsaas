"""MemberSearchProvider — substring match on email + display_name.

Foundation provider. Joins `organisation_members` → `actors` → `users`,
filters by the active org. Email is tenant-scoped PII (org members
already have `read:organisation`). Guests, who never have a
`read:organisation` capability, are filtered out by `is_visible`.
"""

from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.authz import Operation, ResourceType, can
from fastsaas.identity.models import Actor, User
from fastsaas.identity.schemas import CurrentActor
from fastsaas.search.models import SearchHit
from fastsaas.tenants.models import Organisation, OrganisationMember


class MemberSearchProvider:
    entity_type = "member"
    label = "Members"

    async def is_visible(
        self,
        *,
        actor: CurrentActor,
        org_id: UUID,
        is_guest: bool,
        db: AsyncSession,
        cache: Redis | None,
    ) -> bool:
        # Members directory is org-internal. Bundles for owner/admin/member/
        # viewer all mint a `(read, organisation, scope=self)` capability
        # keyed on org_id; guests do not, so this gate cleanly excludes them.
        return await can(
            actor.actor_id,
            Operation.READ,
            ResourceType.ORGANISATION,
            org_id,
            db=db,
            cache=cache,
        )

    async def search(
        self,
        *,
        query: str,
        actor: CurrentActor,
        org_id: UUID,
        limit: int,
        db: AsyncSession,
    ) -> list[SearchHit]:
        like = f"%{query}%"
        org_slug = (
            await db.execute(select(Organisation.slug).where(Organisation.id == org_id))
        ).scalar_one_or_none()
        if org_slug is None:
            return []

        stmt = (
            select(Actor.id, Actor.display_name, User.email)
            .join(OrganisationMember, OrganisationMember.actor_id == Actor.id)
            .join(User, User.actor_id == Actor.id)
            .where(
                OrganisationMember.organisation_id == org_id,
                or_(
                    Actor.display_name.ilike(like),
                    User.email.ilike(like),
                ),
            )
            .order_by(Actor.display_name.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            SearchHit(
                entity_type=self.entity_type,
                entity_id=row.id,
                title=row.display_name,
                subtitle=row.email,
                href=f"/orgs/{org_slug}/settings/members",
            )
            for row in rows
        ]
