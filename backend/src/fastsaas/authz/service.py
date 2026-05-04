"""Capability provisioning — `mint_bundle`, `revoke_bundle`, `mint_capability`,
`revoke_capability`.

All mutations stamp `metadata.org_id` so the `org_admin_scope` RLS policy
(migration 0004) can match. Caller is expected to pass an `org_id` for any
mint inside an org context; resource-scoped one-off grants (UC-001 guest) also
record `metadata.project_id` for traceability.

Cache invalidation is a no-op stub today (TODO in authz/cache.py); it will
flush `caps:{actor_id}` once the cache layer lands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from fastsaas.authz.bundles import BUNDLES, CapabilityTemplate, Scope
from fastsaas.authz.models import Capability


class UnknownBundleError(ValueError):
    """Raised when `bundle_name` is not in BUNDLES."""


class BundleScopeError(ValueError):
    """Raised when bundle templates need a resource_id but the caller did not pass one,
    or when the caller passed `project_ids` for a bundle without `ALL_IN_ORG` scope."""


async def mint_bundle(
    *,
    actor_id: UUID,
    bundle_name: str,
    org_id: UUID,
    granted_by: UUID,
    project_ids: list[UUID] | None = None,
    resource_id: UUID | None = None,
    extra_metadata: dict[str, Any] | None = None,
    db: AsyncSession,
) -> list[Capability]:
    """Mint every capability in `bundle_name` for `actor_id` within `org_id`.

    `project_ids` is required when the bundle contains any `ALL_IN_ORG` template
    (resolved to one row per existing project). `resource_id` is required when
    the bundle contains a `RESOURCE` template (used by `role:guest_viewer`).
    """
    templates = BUNDLES.get(bundle_name)
    if templates is None:
        raise UnknownBundleError(bundle_name)

    needs_resource = any(t.scope is Scope.RESOURCE for t in templates)
    needs_projects = any(t.scope is Scope.ALL_IN_ORG for t in templates)
    if needs_resource and resource_id is None:
        raise BundleScopeError(f"Bundle {bundle_name!r} requires a resource_id")
    if needs_projects and project_ids is None:
        raise BundleScopeError(f"Bundle {bundle_name!r} requires project_ids")

    base_meta: dict[str, Any] = {"org_id": str(org_id)}
    if extra_metadata:
        base_meta.update(extra_metadata)

    created: list[Capability] = []
    for template in templates:
        for resource in _resolve_targets(template, org_id, project_ids, resource_id):
            cap = Capability(
                actor_id=actor_id,
                operation=template.operation.value,
                resource_type=template.resource_type.value,
                resource_id=resource,
                bundle_name=bundle_name,
                granted_by=granted_by,
                meta=dict(base_meta),
            )
            db.add(cap)
            created.append(cap)
    await db.flush()
    return created


async def revoke_bundle(
    *,
    actor_id: UUID,
    bundle_name: str,
    org_id: UUID,
    revoked_by: UUID,
    db: AsyncSession,
) -> int:
    """Soft-revoke every active capability for `actor_id` tagged with this bundle in this org."""
    now = datetime.now(UTC)
    stmt = (
        update(Capability)
        .where(
            Capability.actor_id == actor_id,
            Capability.bundle_name == bundle_name,
            Capability.revoked_at.is_(None),
            Capability.meta["org_id"].astext == str(org_id),
        )
        .values(revoked_at=now)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


async def mint_capability(
    *,
    actor_id: UUID,
    operation: str,
    resource_type: str,
    resource_id: UUID | None,
    granted_by: UUID,
    org_id: UUID | None = None,
    expires_at: datetime | None = None,
    extra_metadata: dict[str, Any] | None = None,
    db: AsyncSession,
) -> Capability:
    """Mint a single one-off capability (no bundle)."""
    meta: dict[str, Any] = {}
    if org_id is not None:
        meta["org_id"] = str(org_id)
    if extra_metadata:
        meta.update(extra_metadata)

    cap = Capability(
        actor_id=actor_id,
        operation=operation,
        resource_type=resource_type,
        resource_id=resource_id,
        granted_by=granted_by,
        expires_at=expires_at,
        meta=meta,
    )
    db.add(cap)
    await db.flush()
    return cap


async def revoke_capability(
    *,
    capability_id: UUID,
    revoked_by: UUID,
    db: AsyncSession,
) -> int:
    """Soft-revoke one capability by id. Returns 1 if it was active, 0 otherwise."""
    now = datetime.now(UTC)
    stmt = (
        update(Capability)
        .where(Capability.id == capability_id, Capability.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    result = await db.execute(stmt)
    return result.rowcount or 0


def _resolve_targets(
    template: CapabilityTemplate,
    org_id: UUID,
    project_ids: list[UUID] | None,
    resource_id: UUID | None,
) -> list[UUID | None]:
    """Map a template scope to one or more concrete `resource_id` values."""
    match template.scope:
        case Scope.SELF:
            # `self` for resource_type=organisation/audit_log refers to the current org.
            # For other resource types treat as type-wide (resource_id NULL).
            if template.resource_type.value in {"organisation", "audit_log", "agent", "service"}:
                return [org_id if template.resource_type.value == "organisation" else None]
            return [None]
        case Scope.ALL_IN_ORG:
            assert project_ids is not None  # guarded by mint_bundle
            return list(project_ids) if project_ids else []
        case Scope.RESOURCE:
            assert resource_id is not None  # guarded by mint_bundle
            return [resource_id]
