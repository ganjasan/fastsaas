"""Capability-based authorization (per ADR-013).

`can(actor, op, resource_type, resource_id?)` is the single authorization API.
Application code goes through `service.mint_bundle` / `service.revoke_bundle`
to grant/revoke; route handlers depend on `dependencies.require_capability(...)`.
"""

from fastsaas.authz.bundles import BUNDLES, Cap, CapabilityTemplate, Operation, ResourceType
from fastsaas.authz.check import can
from fastsaas.authz.dependencies import require_capability
from fastsaas.authz.service import (
    mint_bundle,
    mint_capability,
    revoke_bundle,
    revoke_capability,
)

__all__ = [
    "BUNDLES",
    "Cap",
    "CapabilityTemplate",
    "Operation",
    "ResourceType",
    "can",
    "mint_bundle",
    "mint_capability",
    "require_capability",
    "revoke_bundle",
    "revoke_capability",
]
