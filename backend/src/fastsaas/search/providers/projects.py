"""ProjectSearchProvider — substring match on name / slug / description.

Foundation provider. Org-scoped via the route's `TenantContextDep`
(which pins `app.current_org` for the `app_user` session); RLS on
`projects` does the rest. Soft-deleted projects are excluded.

Per-row authorization: `(read, project)` capabilities are minted with
`scope=all_in_org` (one row per project) for org members and with
`scope=resource` for guests (one row for the shared project). The query
JOINs `capabilities` on the actor + `(read, project)` so each caller
sees exactly the projects they can read — members see all, guests see
their share. The `actor_self_read` RLS policy on `capabilities` allows
the join to read the actor's own caps once `app.current_actor` is
pinned, which TenantContextDep already does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.authz.models import Capability
from fastsaas.identity.schemas import CurrentActor
from fastsaas.search.models import SearchHit
from fastsaas.tenants.models import Organisation, Project


class ProjectSearchProvider:
    entity_type = "project"
    label = "Projects"

    async def is_visible(
        self,
        *,
        actor: CurrentActor,
        org_id: UUID,
        is_guest: bool,
        db: AsyncSession,
        cache: Redis | None,
    ) -> bool:
        # The route's TenantContextDep already enforced that the actor has
        # access to this workspace (member or share-link guest). Per-row
        # filtering happens in `search()`.
        return True

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
        # Pull the org slug so we can build hrefs without a per-row second
        # query. RLS on `organisations` admits the active tenant's row.
        org_row = (
            await db.execute(select(Organisation.slug).where(Organisation.id == org_id))
        ).scalar_one_or_none()
        if org_row is None:
            return []
        org_slug = org_row

        # Inner JOIN against the actor's active read:project capabilities.
        # For org members the (all_in_org) bundle mints one cap per project;
        # for guests, a single resource-scoped cap covers the shared project.
        now = datetime.now(UTC)
        stmt = (
            select(Project.id, Project.name, Project.slug, Project.description)
            .join(Capability, Capability.resource_id == Project.id)
            .where(
                Project.deleted_at.is_(None),
                Capability.actor_id == actor.actor_id,
                Capability.operation == "read",
                Capability.resource_type == "project",
                Capability.revoked_at.is_(None),
                Capability.policy_blocked.is_(False),
                or_(
                    Capability.expires_at.is_(None),
                    Capability.expires_at > now,
                ),
                or_(
                    Project.name.ilike(like),
                    Project.slug.ilike(like),
                    Project.description.ilike(like),
                ),
            )
            .order_by(Project.name.asc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).all()
        return [
            SearchHit(
                entity_type=self.entity_type,
                entity_id=row.id,
                title=row.name,
                subtitle=row.slug,
                href=f"/orgs/{org_slug}/projects/{row.slug}",
            )
            for row in rows
        ]
