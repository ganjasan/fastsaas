"""Platform admin module — staff-gated cross-org surfaces.

Per ADR-019 the admin authority is structural: a boolean column on
`actors` (toggled out-of-band via the seed CLI) makes an actor platform
staff. The `can()` API short-circuits `(PLATFORM_ADMIN, PLATFORM)` checks
against this column without inflating the org-scoped capabilities table.

This package houses staff-only surfaces (the `/admin/...` API and any
service code dedicated to platform-level operations). Subsequent epics
(#20-#23) plug in here:
- #20 — orgs / metrics / health pages
- #21 — auth-page customisation + password policy + registration controls
- #22 — OAuth providers configuration
- #23 — full design-system editor
"""

from fastsaas.admin.dependencies import require_platform_staff
from fastsaas.admin.schemas import AdminMeResponse

__all__ = ["AdminMeResponse", "require_platform_staff"]
