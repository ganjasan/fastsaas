"""URL slug validation for organisations and projects.

The DB enforces the format constraint via `org_slug_format` /
`project_slug_format` CHECK clauses (regex `^[a-z0-9-]{3,63}$`); this module
gives the application layer a friendly error code before round-tripping to
Postgres, plus the reserved-words list which is not in the DB.
"""

from __future__ import annotations

import re

SLUG_RE = re.compile(r"^[a-z0-9-]{3,63}$")

# Words that would clash with platform routes or admin paths. Adjusted
# alongside any change that adds a new top-level route.
RESERVED_SLUGS: frozenset[str] = frozenset(
    {
        "admin",
        "api",
        "app",
        "auth",
        "billing",
        "console",
        "dashboard",
        "docs",
        "help",
        "internal",
        "login",
        "logout",
        "new",
        "oauth",
        "orgs",
        "platform",
        "projects",
        "register",
        "settings",
        "signup",
        "static",
        "status",
        "support",
        "system",
    }
)


class SlugError(ValueError):
    """Slug failed validation. `code` is the API error code returned to clients."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_slug(slug: str, *, kind: str = "org") -> str:
    """Return the slug if valid; raise SlugError otherwise.

    `kind` is "org" or "project"; it shapes the returned error code so the
    frontend can map to the right field.
    """
    if not isinstance(slug, str) or not SLUG_RE.fullmatch(slug):
        raise SlugError(f"{kind}.slug_invalid", f"Invalid {kind} slug: {slug!r}")
    if slug in RESERVED_SLUGS:
        raise SlugError(f"{kind}.slug_reserved", f"Reserved {kind} slug: {slug!r}")
    return slug
