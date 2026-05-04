"""OrganisationService + MembershipService.

Mutations and cross-org reads run through the BYPASSRLS migrator session
(per ADR-007: app code uses migrator role only when there is no
`app.current_org` to satisfy RLS, and for org-bootstrap there isn't yet).
The service layer is the only acceptable home for this — route handlers
must NOT open migrator sessions directly.

`mint_bundle(...)` is invoked inside the same transaction so the new org /
membership / role-change is born with its capabilities already in place.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from fastsaas.authz.bundles import BUNDLES, Scope
from fastsaas.authz.models import Capability
from fastsaas.authz.service import mint_bundle, mint_capability, revoke_bundle
from fastsaas.db import migrator_session_scope
from fastsaas.identity.models import Actor, User
from fastsaas.tenants.models import (
    Organisation,
    OrganisationMember,
    OrganisationRole,
    OrgInvitation,
    Project,
    ProjectShare,
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

        Concurrency: a SELECT-then-INSERT pre-check is racy by itself, so we
        also catch `IntegrityError` on the unique slug index and re-raise as
        `OrgSlugTakenError` — that turns a 500 into the spec-promised 409
        when two POST /orgs requests with the same slug arrive in parallel.
        """
        try:
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
        except IntegrityError as e:
            raise OrgSlugTakenError(slug) from e

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

        `actor_id` is recorded inside `Capability.meta.revoked_by` (audit
        breadcrumb) but NEVER overwrites `granted_by` — that column is
        immutable so audit reconstruction can answer "who originally minted
        this owner bundle?" even after revocation.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            org = await db.get(Organisation, org_id)
            if org is None or org.deleted_at is not None:
                raise OrgNotFoundError(str(org_id))

            org.deleted_at = now
            db.add(org)

            # Revoke every bundle row tagged with this org. Stamp who
            # revoked into metadata; leave `granted_by` (immutable) alone.
            # `meta || jsonb_build_object(...)` merges keys without
            # clobbering pre-existing entries on the row.
            await db.execute(
                update(Capability)
                .where(
                    Capability.meta["org_id"].astext == str(org_id),
                    Capability.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    meta=Capability.meta.op("||")(
                        text(
                            "jsonb_build_object('revoked_by', :rb, 'revoked_at', :ra)"
                        ).bindparams(rb=str(actor_id), ra=now.isoformat())
                    ),
                )
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


# ─────────────────────────────────────────────────────────────────────────────
# Membership
# ─────────────────────────────────────────────────────────────────────────────

INVITE_TTL = timedelta(days=7)
_INVITE_TOKEN_BYTES = 32

_INVITE_ROLES: frozenset[OrganisationRole] = frozenset(
    {
        OrganisationRole.ADMIN,
        OrganisationRole.MEMBER,
        OrganisationRole.VIEWER,
        OrganisationRole.COMPLIANCE_OFFICER,
    }
)


class InviteRoleError(ValueError):
    """Raised when the requested invite role is not in the allowed set
    (e.g. trying to invite as `owner` — owners are minted by org create)."""


class InviteAlreadyMemberError(Exception):
    """Raised when the email already corresponds to an active org member."""


class InviteNotFoundError(Exception):
    """Raised when accept-invite cannot find an active token (unknown,
    consumed, or expired). Callers map to 404 to avoid leaking which."""


class MemberNotFoundError(Exception):
    """Raised when targeting a non-existent membership for change_role/remove."""


class LastOwnerError(Exception):
    """Raised when an action would leave the org with zero owners
    (BR equivalent: every org must keep at least one OWNER)."""


def _hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _bundle_for(role: OrganisationRole) -> str:
    return f"role:{role.value}"


class MembershipService:
    """Invite / accept / change-role / remove / list.

    Uses the migrator session for the same reason OrganisationService does:
    invites cross the unauthenticated boundary (accept happens before
    tenant_context can pin app.current_org), and role-change / removal
    must atomically revoke + mint capability bundles.
    """

    # ── Invitations ─────────────────────────────────────────────────────────

    @staticmethod
    async def invite(
        *,
        org_id: UUID,
        email: str,
        role: OrganisationRole,
        invited_by: UUID,
    ) -> tuple[str, OrgInvitation]:
        """Mint an invitation token. Returns `(raw_token, row)`; the caller
        emails the raw token and discards it.

        Refuses to invite for `OrganisationRole.OWNER` — owners are minted
        only by `OrganisationService.create`. Refuses to invite an email
        that already maps to an active member of this org.
        """
        if role not in _INVITE_ROLES:
            raise InviteRoleError(role.value)

        async with migrator_session_scope() as db:
            existing_member_actor = await _find_member_actor_id(
                db, org_id=org_id, email=email
            )
            if existing_member_actor is not None:
                raise InviteAlreadyMemberError(email)

            raw = secrets.token_urlsafe(_INVITE_TOKEN_BYTES)
            inv = OrgInvitation(
                organisation_id=org_id,
                email=email,
                role=role.value,
                token_hash=_hash_invite_token(raw),
                invited_by=invited_by,
                expires_at=datetime.now(UTC) + INVITE_TTL,
            )
            db.add(inv)
            await db.flush()
            await db.refresh(inv)
            return raw, inv

    @staticmethod
    async def accept(
        *, raw_token: str, accepting_actor_id: UUID
    ) -> tuple[Organisation, OrganisationRole]:
        """Consume the invitation, insert the membership row, and mint the
        target role bundle — all in one transaction.

        Order matters: we look up the invite first, decide whether the
        accepting actor is already a member, and only burn the token when
        we'll actually do work. Re-acceptance by an existing member is a
        no-op that returns the **existing** role and leaves the invite
        unconsumed (so an admin can re-issue or use change_role explicitly
        rather than getting a silently-burned token with the wrong role).

        The accepting actor must already exist (registered + verified). The
        actor's email is NOT required to match the invitation's email: that
        constraint is enforced at the route layer where the bearer token
        identifies the caller.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            inv = (
                await db.execute(
                    select(OrgInvitation).where(
                        OrgInvitation.token_hash == _hash_invite_token(raw_token),
                        OrgInvitation.consumed_at.is_(None),
                        OrgInvitation.expires_at > now,
                    )
                )
            ).scalar_one_or_none()
            if inv is None:
                raise InviteNotFoundError("invite_not_found_or_expired")

            org = await db.get(Organisation, inv.organisation_id)
            if org is None or org.deleted_at is not None:
                raise InviteNotFoundError("org_unavailable")

            # Idempotent re-acceptance: actor is already a member of this
            # org. Do not burn the token — admins can still see the
            # invite as pending and either revoke it or use change_role
            # to actually move the member. Return the **existing** role.
            existing_membership = await db.get(
                OrganisationMember, (org.id, accepting_actor_id)
            )
            if existing_membership is not None:
                return org, OrganisationRole(existing_membership.role)

            # Atomic consume — guards against a concurrent accept of the
            # same token between the SELECT above and this UPDATE. If
            # someone else won, we surface InviteNotFoundError so the
            # caller sees a clean 404.
            consumed = (
                await db.execute(
                    update(OrgInvitation)
                    .where(
                        OrgInvitation.id == inv.id,
                        OrgInvitation.consumed_at.is_(None),
                    )
                    .values(consumed_at=now, consumed_by=accepting_actor_id)
                    .returning(OrgInvitation.id)
                )
            ).scalar_one_or_none()
            if consumed is None:
                raise InviteNotFoundError("invite_not_found_or_expired")

            role = OrganisationRole(inv.role)
            db.add(
                OrganisationMember(
                    organisation_id=org.id,
                    actor_id=accepting_actor_id,
                    role=role,
                )
            )

            project_ids = [
                p.id
                for p in (await db.execute(
                    select(Project).where(
                        Project.organisation_id == org.id,
                        Project.deleted_at.is_(None),
                    )
                )).scalars().all()
            ]

            await mint_bundle(
                actor_id=accepting_actor_id,
                bundle_name=_bundle_for(role),
                org_id=org.id,
                granted_by=inv.invited_by,
                project_ids=project_ids,
                db=db,
            )
            return org, role

    # ── Role change / removal ───────────────────────────────────────────────

    @staticmethod
    async def change_role(
        *,
        org_id: UUID,
        target_actor_id: UUID,
        new_role: OrganisationRole,
        actor_id: UUID,
    ) -> None:
        """Revoke the previous bundle and mint the new one in one TX.

        Refuses to demote the last OWNER — every active org must keep
        at least one. Refuses to demote/promote `compliance_officer` into
        an operational role via this endpoint (Phase 2 will add a
        dedicated compliance-officer flow with stronger audit).
        """
        async with migrator_session_scope() as db:
            member = await db.get(OrganisationMember, (org_id, target_actor_id))
            if member is None:
                raise MemberNotFoundError(str(target_actor_id))

            old_role = OrganisationRole(member.role)
            if old_role == new_role:
                return  # idempotent no-op

            if old_role is OrganisationRole.OWNER:
                await _assert_not_last_owner(db, org_id=org_id)

            old_bundle = _bundle_for(old_role)
            new_bundle = _bundle_for(new_role)

            await revoke_bundle(
                actor_id=target_actor_id,
                bundle_name=old_bundle,
                org_id=org_id,
                revoked_by=actor_id,
                db=db,
            )

            project_ids = [
                p.id
                for p in (await db.execute(
                    select(Project).where(
                        Project.organisation_id == org_id,
                        Project.deleted_at.is_(None),
                    )
                )).scalars().all()
            ]

            await mint_bundle(
                actor_id=target_actor_id,
                bundle_name=new_bundle,
                org_id=org_id,
                granted_by=actor_id,
                project_ids=project_ids,
                db=db,
            )

            member.role = new_role
            db.add(member)

    @staticmethod
    async def remove(
        *, org_id: UUID, target_actor_id: UUID, actor_id: UUID
    ) -> None:
        """Delete the membership row and revoke every active bundle this
        actor holds within this org. Refuses to remove the last OWNER."""
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            member = await db.get(OrganisationMember, (org_id, target_actor_id))
            if member is None:
                raise MemberNotFoundError(str(target_actor_id))

            if OrganisationRole(member.role) is OrganisationRole.OWNER:
                await _assert_not_last_owner(db, org_id=org_id)

            await db.delete(member)

            await db.execute(
                update(Capability)
                .where(
                    Capability.actor_id == target_actor_id,
                    Capability.meta["org_id"].astext == str(org_id),
                    Capability.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    meta=Capability.meta.op("||")(
                        text(
                            "jsonb_build_object('revoked_by', :rb, 'revoked_at', :ra)"
                        ).bindparams(rb=str(actor_id), ra=now.isoformat())
                    ),
                )
            )

    # ── Reads ───────────────────────────────────────────────────────────────

    @staticmethod
    async def list_members(
        org_id: UUID,
    ) -> list[tuple[OrganisationMember, str | None, str | None]]:
        """Return (member, email, display_name) per active membership.

        `email` is `None` for non-HUMAN actors (no `users` row). Sorted
        by created_at ascending so the UI shows joining order.
        """
        async with migrator_session_scope() as db:
            stmt = (
                select(OrganisationMember, User.email, Actor.display_name)
                .join(Actor, Actor.id == OrganisationMember.actor_id)
                .join(User, User.actor_id == Actor.id, isouter=True)
                .where(
                    OrganisationMember.organisation_id == org_id,
                    Actor.deleted_at.is_(None),
                )
                .order_by(OrganisationMember.created_at.asc())
            )
            rows = (await db.execute(stmt)).all()
            return [(m, email, name) for (m, email, name) in rows]

    @staticmethod
    async def list_pending_invites(org_id: UUID) -> list[OrgInvitation]:
        """Active (non-consumed, non-expired) invitations for an org.
        Used by the admin members page to show "1 pending invite" alongside
        actual members.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            stmt = (
                select(OrgInvitation)
                .where(
                    OrgInvitation.organisation_id == org_id,
                    OrgInvitation.consumed_at.is_(None),
                    OrgInvitation.expires_at > now,
                )
                .order_by(OrgInvitation.created_at.asc())
            )
            return list((await db.execute(stmt)).scalars().all())


# ── Internal helpers ────────────────────────────────────────────────────────


async def _find_member_actor_id(db, *, org_id: UUID, email: str) -> UUID | None:
    """Resolve email → actor_id → membership in one query (HUMAN actors only)."""
    stmt = (
        select(OrganisationMember.actor_id)
        .join(User, User.actor_id == OrganisationMember.actor_id)
        .where(
            OrganisationMember.organisation_id == org_id,
            User.email == email,
        )
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def _assert_not_last_owner(db, *, org_id: UUID) -> None:
    """Raise LastOwnerError if removing/demoting the only active OWNER."""
    stmt = select(OrganisationMember).where(
        OrganisationMember.organisation_id == org_id,
        OrganisationMember.role == OrganisationRole.OWNER,
    )
    owners = (await db.execute(stmt)).scalars().all()
    if len(owners) <= 1:
        raise LastOwnerError(str(org_id))


# ─────────────────────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────────────────────


class ProjectSlugTakenError(Exception):
    """Raised when a project with this slug already exists in the org."""


class ProjectNotFoundError(Exception):
    """Raised when targeting a non-existent (or soft-deleted) project."""


class ProjectService:
    """Encapsulates project-level domain operations.

    `create` is the only mutation that needs to fan out — when a new project
    appears, every active member's `all_in_org` bundle templates need a
    matching capability row scoped to the new project's id (otherwise their
    bundle wouldn't actually grant anything on this new project). This is
    done in the same transaction as the project insert so the project is
    never visible without the matching grants.
    """

    @staticmethod
    async def create(
        *,
        org_id: UUID,
        name: str,
        slug: str,
        description: str | None,
        created_by: UUID,
    ) -> Project:
        try:
            async with migrator_session_scope() as db:
                existing = (
                    await db.execute(
                        select(Project.id).where(
                            Project.organisation_id == org_id,
                            Project.slug == slug,
                        ).limit(1)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    raise ProjectSlugTakenError(slug)

                project = Project(
                    organisation_id=org_id,
                    name=name,
                    slug=slug,
                    description=description,
                    created_by=created_by,
                )
                db.add(project)
                await db.flush()

                # Fan out `all_in_org` bundle templates for every active
                # member: one capability row per (member, template).
                members = (
                    await db.execute(
                        select(OrganisationMember).where(
                            OrganisationMember.organisation_id == org_id,
                        )
                    )
                ).scalars().all()
                for m in members:
                    bundle_name = f"role:{OrganisationRole(m.role).value}"
                    templates = BUNDLES.get(bundle_name, [])
                    for t in templates:
                        if t.scope is not Scope.ALL_IN_ORG:
                            continue
                        if t.resource_type.value != "project":
                            continue
                        await mint_capability(
                            actor_id=m.actor_id,
                            operation=t.operation.value,
                            resource_type=t.resource_type.value,
                            resource_id=project.id,
                            granted_by=created_by,
                            org_id=org_id,
                            bundle_name=bundle_name,
                            db=db,
                        )

                await db.refresh(project)
                return project
        except IntegrityError as e:
            raise ProjectSlugTakenError(slug) from e

    @staticmethod
    async def list_in_org(org_id: UUID) -> list[Project]:
        async with migrator_session_scope() as db:
            stmt = (
                select(Project)
                .where(
                    Project.organisation_id == org_id,
                    Project.deleted_at.is_(None),
                )
                .order_by(Project.created_at.asc())
            )
            return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def get_by_slug(*, org_id: UUID, slug: str) -> Project | None:
        async with migrator_session_scope() as db:
            stmt = select(Project).where(
                Project.organisation_id == org_id,
                Project.slug == slug,
                Project.deleted_at.is_(None),
            )
            return (await db.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def update(
        *,
        project_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Project:
        async with migrator_session_scope() as db:
            project = await db.get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise ProjectNotFoundError(str(project_id))
            if name is not None:
                project.name = name
            if description is not None:
                project.description = description
            db.add(project)
            await db.flush()
            await db.refresh(project)
            return project

    @staticmethod
    async def soft_delete(*, project_id: UUID, actor_id: UUID) -> None:
        """Soft-delete the project. Capability rows scoped to the project are
        left in place — restore (Phase 2 backlog) re-uses them. Listing
        endpoints filter on `deleted_at IS NULL`, which is enough."""
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            project = await db.get(Project, project_id)
            if project is None or project.deleted_at is not None:
                raise ProjectNotFoundError(str(project_id))
            project.deleted_at = now
            db.add(project)
            # NB: actor_id intentionally unused here — soft-delete leaves a
            # trail in the soon-to-be audit_log middleware (#4), not on
            # Project itself. Keeping the parameter on the signature so
            # the audit hook can grow without changing call sites.
            _ = actor_id


# ─────────────────────────────────────────────────────────────────────────────
# Project shares (UC-001 — per-project guest)
# ─────────────────────────────────────────────────────────────────────────────


SHARE_DEFAULT_TTL = timedelta(days=14)
SHARE_MAX_TTL = timedelta(days=30)


class ShareTTLError(ValueError):
    """Raised when a caller asks for a TTL above SHARE_MAX_TTL."""


class ShareNotFoundError(Exception):
    """Raised on accept when the token is unknown / consumed / expired."""


class ProjectShareService:
    """Mints and consumes per-project guest tokens (UC-001).

    Distinct from MembershipService.invite/accept because the resulting
    capability is resource-scoped (one project) and does NOT create an
    organisation_members row. Guests pass through tenant_context via the
    is_guest path defined in tenants.dependencies.
    """

    @staticmethod
    async def share(
        *,
        org_id: UUID,
        project_id: UUID,
        email: str,
        shared_by: UUID,
        ttl: timedelta | None = None,
    ) -> tuple[str, ProjectShare]:
        """Mint a per-project share token. Returns `(raw_token, row)`."""
        ttl = ttl or SHARE_DEFAULT_TTL
        if ttl > SHARE_MAX_TTL:
            raise ShareTTLError(f"ttl exceeds {SHARE_MAX_TTL.days}d cap")

        async with migrator_session_scope() as db:
            raw = secrets.token_urlsafe(_INVITE_TOKEN_BYTES)
            row = ProjectShare(
                project_id=project_id,
                organisation_id=org_id,
                email=email,
                token_hash=_hash_invite_token(raw),
                shared_by=shared_by,
                expires_at=datetime.now(UTC) + ttl,
            )
            db.add(row)
            await db.flush()
            await db.refresh(row)
            return raw, row

    @staticmethod
    async def accept(
        *, raw_token: str, accepting_actor_id: UUID
    ) -> tuple[Organisation, Project]:
        """Consume the share and mint a `read:project` capability scoped
        to the shared project, linking the capability id back onto the
        share row for audit / revocation.

        The atomic UPDATE...RETURNING below also enforces single-use even
        under concurrent accept attempts: at most one mint per token.

        If the accepting actor is already a member of the share's org we
        consume the token (single-use is part of the contract) but skip
        the mint — a `role:guest_viewer` row would never be reached by
        `revoke_bundle('role:member', ...)` cleanup, so it would linger
        as a stray capability until expiry. The member already has
        access via `all_in_org`, so the mint adds nothing.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            stmt = (
                update(ProjectShare)
                .where(
                    ProjectShare.token_hash == _hash_invite_token(raw_token),
                    ProjectShare.consumed_at.is_(None),
                    ProjectShare.expires_at > now,
                )
                .values(consumed_at=now, consumed_by=accepting_actor_id)
                .returning(ProjectShare)
            )
            share = (await db.execute(stmt)).scalar_one_or_none()
            if share is None:
                raise ShareNotFoundError("share_not_found_or_expired")

            project = await db.get(Project, share.project_id)
            if project is None or project.deleted_at is not None:
                raise ShareNotFoundError("project_unavailable")

            org = await db.get(Organisation, share.organisation_id)
            if org is None or org.deleted_at is not None:
                raise ShareNotFoundError("org_unavailable")

            existing_membership = await db.get(
                OrganisationMember, (org.id, accepting_actor_id)
            )
            if existing_membership is not None:
                # Member already has access through their org bundle.
                # Token is consumed (above), capability not minted.
                return org, project

            cap = await mint_capability(
                actor_id=accepting_actor_id,
                operation="read",
                resource_type="project",
                resource_id=project.id,
                granted_by=share.shared_by,
                org_id=org.id,
                bundle_name="role:guest_viewer",
                expires_at=share.expires_at,
                extra_metadata={
                    "share_id": str(share.id),
                    "project_id": str(project.id),
                },
                db=db,
            )

            share.consumed_capability_id = cap.id
            db.add(share)
            await db.flush()
            return org, project

    @staticmethod
    async def list_pending_for_project(
        *, organisation_id: UUID, project_id: UUID
    ) -> list[ProjectShare]:
        """Active (non-consumed, non-expired) shares for a project.

        `organisation_id` is required for defence-in-depth: this runs on
        the BYPASSRLS migrator session, so a future caller passing only
        `project_id` could otherwise pull a row that belongs to a
        different org. The route layer always knows the pinned org via
        `tenant_context`, so requiring it here costs nothing.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            stmt = (
                select(ProjectShare)
                .where(
                    ProjectShare.organisation_id == organisation_id,
                    ProjectShare.project_id == project_id,
                    ProjectShare.consumed_at.is_(None),
                    ProjectShare.expires_at > now,
                )
                .order_by(ProjectShare.created_at.asc())
            )
            return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def revoke(*, share_id: UUID, revoked_by: UUID) -> None:
        """Cancel a pending or active share. Soft-revokes the consumed
        capability if one exists; marks the share row consumed so it can
        no longer be redeemed.

        Mirrors the soft-delete semantics elsewhere — never deletes the
        share row, so a forensic timeline survives.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            share = await db.get(ProjectShare, share_id)
            if share is None:
                raise ShareNotFoundError(str(share_id))

            if share.consumed_at is None:
                # Pending invite: just stamp consumed so it can't be redeemed.
                share.consumed_at = now
                share.consumed_by = revoked_by
                db.add(share)
                await db.flush()
                return

            # Already consumed — revoke the resulting capability if still active.
            if share.consumed_capability_id is None:
                return  # nothing to do
            await db.execute(
                update(Capability)
                .where(
                    Capability.id == share.consumed_capability_id,
                    Capability.revoked_at.is_(None),
                )
                .values(
                    revoked_at=now,
                    meta=Capability.meta.op("||")(
                        text(
                            "jsonb_build_object('revoked_by', :rb, 'revoked_at', :ra)"
                        ).bindparams(rb=str(revoked_by), ra=now.isoformat())
                    ),
                )
            )
