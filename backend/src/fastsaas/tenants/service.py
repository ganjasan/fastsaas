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

from fastsaas.authz.models import Capability
from fastsaas.authz.service import mint_bundle, revoke_bundle
from fastsaas.db import migrator_session_scope
from fastsaas.identity.models import Actor, User
from fastsaas.tenants.models import (
    Organisation,
    OrganisationMember,
    OrganisationRole,
    OrgInvitation,
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

        The accepting actor must already exist (i.e. registered + verified
        through the auth flow). The accepting actor's email is NOT required
        to match the invitation's email: that constraint is enforced at
        the route layer where we have the bearer token's identity.
        """
        now = datetime.now(UTC)
        async with migrator_session_scope() as db:
            stmt = (
                update(OrgInvitation)
                .where(
                    OrgInvitation.token_hash == _hash_invite_token(raw_token),
                    OrgInvitation.consumed_at.is_(None),
                    OrgInvitation.expires_at > now,
                )
                .values(consumed_at=now, consumed_by=accepting_actor_id)
                .returning(OrgInvitation)
            )
            inv = (await db.execute(stmt)).scalar_one_or_none()
            if inv is None:
                raise InviteNotFoundError("invite_not_found_or_expired")

            org = await db.get(Organisation, inv.organisation_id)
            if org is None or org.deleted_at is not None:
                raise InviteNotFoundError("org_unavailable")

            # Already a member? Idempotent re-acceptance is allowed:
            # we don't insert a duplicate, but we also don't re-mint
            # capabilities — they already exist for the active bundle.
            existing_membership = await db.get(
                OrganisationMember, (org.id, accepting_actor_id)
            )
            if existing_membership is not None:
                return org, OrganisationRole(existing_membership.role)

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
