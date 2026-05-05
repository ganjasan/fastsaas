"""Role bundles — capability templates assigned in code (per ADR-013 §D2).

A bundle is a fixed list of capability templates. Assigning `role:owner` to an
actor mints one capability row per template, each tagged with
`bundle_name='role:owner'`. `Scope` controls how `resource_id` is resolved at
mint time:

- `SELF` — `resource_id = org.id` (for `organisation` / `audit_log`).
- `ALL_IN_ORG` — one row per existing project in the org; new projects get a
  follow-up row from `ProjectService.create` for every active member bundle.
- `RESOURCE` — caller passes explicit `resource_id` (used by guest invites).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Operation(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    RUN = "run"
    ADMIN = "admin"
    SHARE = "share"
    GRANT = "grant"
    SCRUB = "scrub"


class ResourceType(StrEnum):
    ORGANISATION = "organisation"
    PROJECT = "project"
    SCENARIO = "scenario"
    AUDIT_LOG = "audit_log"
    AGENT = "agent"
    SERVICE = "service"
    WILDCARD = "*"


class Scope(StrEnum):
    SELF = "self"
    ALL_IN_ORG = "all_in_org"
    RESOURCE = "resource"


@dataclass(frozen=True, slots=True)
class CapabilityTemplate:
    operation: Operation
    resource_type: ResourceType
    scope: Scope


def Cap(op: str, resource: str, *, scope: str = "self") -> CapabilityTemplate:  # noqa: N802 — `Cap` reads as a literal in the bundle table; lowercase loses that.
    """Shorthand factory used by `BUNDLES`."""
    return CapabilityTemplate(
        operation=Operation(op),
        resource_type=ResourceType(resource),
        scope=Scope(scope),
    )


BUNDLES: dict[str, list[CapabilityTemplate]] = {
    "role:owner": [
        # admin/share imply read for the same resource type, but `can()` is a
        # literal predicate (no implication graph), so we mint the read row
        # explicitly. Otherwise GET /orgs/{slug}/members and similar reads
        # would 403 for owners.
        Cap("read",   "organisation", scope="self"),
        Cap("admin",  "organisation", scope="self"),
        Cap("share",  "organisation", scope="self"),
        Cap("admin",  "project",      scope="all_in_org"),
        Cap("share",  "project",      scope="all_in_org"),
        Cap("write",  "project",      scope="all_in_org"),
        Cap("run",    "project",      scope="all_in_org"),
        Cap("read",   "project",      scope="all_in_org"),
        Cap("read",   "audit_log",    scope="self"),
        Cap("grant",  "agent",        scope="self"),
        Cap("grant",  "service",      scope="self"),
    ],
    "role:admin": [
        Cap("read",  "organisation", scope="self"),
        Cap("admin", "organisation", scope="self"),
        Cap("admin", "project",   scope="all_in_org"),
        Cap("share", "project",   scope="all_in_org"),
        Cap("write", "project",   scope="all_in_org"),
        Cap("run",   "project",   scope="all_in_org"),
        Cap("read",  "project",   scope="all_in_org"),
        Cap("read",  "audit_log", scope="self"),
    ],
    "role:member": [
        Cap("read",  "organisation", scope="self"),
        Cap("write", "project",      scope="all_in_org"),
        Cap("run",   "project",      scope="all_in_org"),
        Cap("read",  "project",      scope="all_in_org"),
    ],
    "role:viewer": [
        Cap("read", "organisation", scope="self"),
        Cap("read", "project",      scope="all_in_org"),
    ],
    "role:guest_viewer": [
        # Resource-scoped: caller of mint_bundle must pass resource_id.
        Cap("read", "project", scope="resource"),
    ],
    "role:compliance_officer": [
        Cap("read", "audit_log", scope="self"),
    ],
    "role:dpo": [
        # Data Protection Officer — handles GDPR Art.17 erasure requests.
        # `read` so the DPO can locate rows; `scrub` so they can erase PII.
        # Compliance officer keeps `read` only — read and erase are
        # different responsibilities under GDPR.
        Cap("read",  "audit_log", scope="self"),
        Cap("scrub", "audit_log", scope="self"),
    ],
}


# Bundles that the membership service treats as "primary" (drives the
# denormalised `organisation_members.role`). One per actor per org.
PRIMARY_BUNDLES: frozenset[str] = frozenset(
    {
        "role:owner",
        "role:admin",
        "role:member",
        "role:viewer",
        "role:compliance_officer",
        "role:dpo",
    }
)
