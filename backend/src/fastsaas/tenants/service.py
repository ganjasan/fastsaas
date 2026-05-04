"""OrganisationService — create / list / soft-delete orgs.

Mutations and cross-org reads run through the BYPASSRLS migrator session
(per ADR-007: app code uses migrator role only when there is no
`app.current_org` to satisfy RLS, and for org-bootstrap there isn't yet).
The service layer is the only acceptable home for this — route handlers
must NOT open migrator sessions directly.

`mint_bundle('role:owner', ...)` is invoked inside the same transaction so
the new org is born with its owner's capabilities already in place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update

from fastsaas.authz.models import Capability
from fastsaas.authz.service import mint_bundle
from fastsaas.db import migrator_session_scope
from fastsaas.tenants.models import (
    Organisation,
    OrganisationMember,
    OrganisationRole,
    Project,
)


class OrgSlugTakenError(Exception):
    """Raised when an org with this slug already exists (active or deleted)."""


class OrgNotFoundError(Exception):
    """Raised when the org cannot be soft-deleted because it doesn't exist."""


class OrganisationService:
    """Encapsulates org-level domain operations. Static methods only — the
    service has no per-instance state; grouping under a class keeps the
    public surface tidy and import sites readable."""

    @staticmethod
    async def create(
        *, name: str, slug: str, owner_actor_id: UUID
    ) -> Organisation:
        """Create an org with the calling HUMAN actor as owner.

        One transaction:
        1. Insert `organisations` (slug uniqueness enforced by `idx_orgs_slug`).
        2. Insert `organisation_members` for the owner with role=owner.
        3. Mint `role:owner` capabilities (no projects yet → empty
           `project_ids`; the `all_in_org` templates therefore mint zero
           rows, which is fine — `ProjectService.create` will mint them
           later for every active member bundle).
        """
        async with migrator_session_scope() as db:
            existing = (
                await db.execute(
                    select(Organisation.id).where(Organisation.slug == slug).limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                raise OrgSlugTakenError(slug)

            org = Organisation(name=name, slug=slug)
            db.add(org)
            await db.flush()

            db.add(
                OrganisationMember(
                    organisation_id=org.id,
                    actor_id=owner_actor_id,
                    role=OrganisationRole.OWNER,
                )
            )

            await mint_bundle(
                actor_id=owner_actor_id,
                bundle_name="role:owner",
                org_id=org.id,
                granted_by=owner_actor_id,  # self-grant on create
                project_ids=[],
                db=db,
            )

            await db.flush()
            await db.refresh(org)
            return org

    @staticmethod
    async def list_for_actor(actor_id: UUID) -> list[tuple[Organisation, OrganisationRole]]:
        """Return (org, role) for every active org the actor is a member of.

        Uses the migrator session because the caller has no pinned
        `app.current_org` yet — they're choosing one. Soft-deleted orgs are
        filtered out.
        """
        async with migrator_session_scope() as db:
            stmt = (
                select(Organisation, OrganisationMember.role)
                .join(OrganisationMember, OrganisationMember.organisation_id == Organisation.id)
                .where(
                    OrganisationMember.actor_id == actor_id,
                    Organisation.deleted_at.is_(None),
                )
                .order_by(Organisation.created_at.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [(org, OrganisationRole(role)) for (org, role) in rows]

    @staticmethod
    async def soft_delete(*, org_id: UUID, actor_id: UUID) -> None:
        """Soft-delete the org and revoke every bundle granted within it.

        Caller must already have verified `can(admin, organisation, org_id)`.
        Soft-deleted orgs disappear from `_resolve_membership` and from
        `list_for_actor`, so members lose visibility on the next request.

        Active projects are NOT individually marked deleted — they live
        under the org and are filtered by `Organisation.deleted_at IS NULL`
        wherever they're listed.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            org = await db.get(Organisation, org_id)
            if org is None or org.deleted_at is not None:
                raise OrgNotFoundError(str(org_id))

            org.deleted_at = now
            db.add(org)

            # Revoke every bundle row tagged with this org.
            await db.execute(
                update(Capability)
                .where(
                    Capability.meta["org_id"].astext == str(org_id),
                    Capability.revoked_at.is_(None),
                )
                .values(revoked_at=now, granted_by=actor_id)
            )

    @staticmethod
    async def list_projects(org_id: UUID) -> list[Project]:
        """Helper for the project provisioning hook (needed when minting
        `all_in_org` bundle templates for a newly-added member)."""
        async with migrator_session_scope() as db:
            stmt = select(Project).where(
                Project.organisation_id == org_id,
                Project.deleted_at.is_(None),
            )
            return list((await db.execute(stmt)).scalars().all())
