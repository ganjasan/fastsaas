"""Tenant-context FastAPI dependency (per design.md §D4).

Routes scoped to `/orgs/{slug}/...` declare `Depends(tenant_context)`. The
dependency:

1. Pulls `slug` from path params; the calling actor from `current_actor`.
2. Resolves the org + membership (or guest capability) via a short-lived
   BYPASSRLS migrator session — needed because the per-request `app_user`
   session has not yet had `app.current_org` set, so RLS would otherwise
   return 0 rows and we couldn't tell "missing" from "forbidden".
3. Sets `app.current_org` and `app.current_actor` LOCAL on the request's
   `app_user` session (the same session FastAPI hands to the route via
   `SessionDep`, thanks to per-request dependency caching).
4. Returns a `TenantContext(org, actor, is_guest)`.

Non-member / unknown-slug requests get HTTP 404 with
`code = "org.not_found_or_forbidden"` (existence is never disclosed).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy import or_, select, text

from fastsaas.authz.models import Capability
from fastsaas.db import migrator_session_scope
from fastsaas.identity.middleware import SessionDep, current_actor
from fastsaas.identity.schemas import CurrentActor
from fastsaas.tenants.models import Organisation, OrganisationMember, Project


@dataclass(frozen=True, slots=True)
class TenantContext:
    org: Organisation
    actor: CurrentActor
    is_guest: bool


async def _resolve_membership(
    *, slug: str, actor_id
) -> tuple[Organisation, bool] | None:
    """Look up org by slug + membership/guest status. Returns None for unknown
    slug or for actors without any access; (org, is_guest) otherwise.

    Runs through the BYPASSRLS migrator session because at this point we have
    no `app.current_org` to satisfy RLS on `organisations`.
    """
    async with migrator_session_scope() as s:
        org = (
            await s.execute(
                select(Organisation).where(
                    Organisation.slug == slug,
                    Organisation.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if org is None:
            return None

        member = (
            await s.execute(
                select(OrganisationMember).where(
                    OrganisationMember.organisation_id == org.id,
                    OrganisationMember.actor_id == actor_id,
                )
            )
        ).scalar_one_or_none()
        if member is not None:
            return org, False

        # Guest path (UC-001): an active, unexpired capability tagged with
        # this org's id. We mirror `can()` semantics here (revoked / blocked /
        # expired all bar access) so an expired share-link does NOT pass
        # tenant_context — the alternative would route the user past the 404
        # layer and into a deeper 403, which is a worse UX and a small
        # information leak.
        now = datetime.now(UTC)
        guest_cap = (
            await s.execute(
                select(Capability)
                .where(
                    Capability.actor_id == actor_id,
                    Capability.revoked_at.is_(None),
                    Capability.policy_blocked.is_(False),
                    or_(
                        Capability.expires_at.is_(None),
                        Capability.expires_at > now,
                    ),
                    Capability.meta["org_id"].astext == str(org.id),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if guest_cap is not None:
            return org, True

        return None


async def tenant_context(
    slug: str,
    actor: Annotated[CurrentActor, Depends(current_actor)],
    db: SessionDep,
) -> TenantContext:
    """Resolve and pin the tenant context for `/orgs/{slug}/...` routes."""
    resolved = await _resolve_membership(slug=slug, actor_id=actor.actor_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "org.not_found_or_forbidden"},
        )
    org, is_guest = resolved

    # Pin RLS context on the request session. Both the route and any
    # dependent (e.g. require_capability) use the same session via FastAPI
    # per-request Depends caching, so the LOCAL setting holds for the
    # whole request transaction. `set_config(..., true)` is the
    # parameter-friendly equivalent of `SET LOCAL`; Postgres rejects
    # placeholders in plain `SET LOCAL` syntax.
    await db.execute(
        text("SELECT set_config('app.current_org', :id, true)"),
        {"id": str(org.id)},
    )
    await db.execute(
        text("SELECT set_config('app.current_actor', :id, true)"),
        {"id": str(actor.actor_id)},
    )

    return TenantContext(org=org, actor=actor, is_guest=is_guest)


TenantContextDep = Annotated[TenantContext, Depends(tenant_context)]


async def require_org_member(ctx: TenantContextDep) -> TenantContext:
    """Variant that rejects guests — for routes that should not be reachable
    via per-project shares (e.g. listing org members)."""
    if ctx.is_guest:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "org.not_found_or_forbidden"},
        )
    return ctx


@dataclass(frozen=True, slots=True)
class ProjectContext:
    """Sub-context resolved by `project_context`. Inherits the actor + org
    from `tenant_context` and adds the resolved `project` row.
    `is_guest` is propagated unchanged."""

    org: Organisation
    actor: CurrentActor
    project: Project
    is_guest: bool


async def project_context(
    project_slug: str,
    ctx: TenantContextDep,
    db: SessionDep,
) -> ProjectContext:
    """Resolve `project_slug` within the pinned org. 404 if missing /
    soft-deleted — same shape as the org-level miss to avoid leaking which
    projects exist in an org the caller can otherwise see.

    SELECTs against `projects` rely on `app.current_org` already being set
    by `tenant_context`, so the RLS `tenant_isolation` policy
    short-circuits any cross-org leak even if the slug were guessed.
    """
    proj = (
        await db.execute(
            select(Project).where(
                Project.organisation_id == ctx.org.id,
                Project.slug == project_slug,
                Project.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if proj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "project.not_found_or_forbidden"},
        )
    return ProjectContext(org=ctx.org, actor=ctx.actor, project=proj, is_guest=ctx.is_guest)


ProjectContextDep = Annotated[ProjectContext, Depends(project_context)]
