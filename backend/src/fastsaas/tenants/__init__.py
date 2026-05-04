"""Multi-tenant model + access (per ADR-007 + ADR-013).

Implemented in sub-issue #3 (Multi-tenant orgs + capability-based access).
"""

from fastsaas.tenants.dependencies import (
    TenantContext,
    TenantContextDep,
    require_org_member,
    tenant_context,
)
from fastsaas.tenants.models import (
    Organisation,
    OrganisationMember,
    OrganisationRole,
    Project,
)
from fastsaas.tenants.slugs import (
    RESERVED_SLUGS,
    SLUG_RE,
    SlugError,
    validate_slug,
)

__all__ = [
    "RESERVED_SLUGS",
    "SLUG_RE",
    "Organisation",
    "OrganisationMember",
    "OrganisationRole",
    "Project",
    "SlugError",
    "TenantContext",
    "TenantContextDep",
    "require_org_member",
    "tenant_context",
    "validate_slug",
]
