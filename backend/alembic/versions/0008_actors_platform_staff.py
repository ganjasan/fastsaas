"""actors.is_platform_staff — boolean flag for platform-level admin actors.

Companion to the platform-admin-foundation change (issue
ganjasan/fastsaas#19). Per ADR-013 the org-level capability model is
bundle-driven; platform-level authority is structural — a flag on the
actor row, not a capability bundle. The `can()` API short-circuits checks
for `(Operation.PLATFORM_ADMIN, ResourceType.PLATFORM)` against this
column, preserving the "capability is the only authz API" rule for
callers without inflating the capabilities table with cross-org rows.

Default `FALSE`; existing rows inherit the default. The very first staff
member is bootstrapped via `make seed-platform-staff USER_EMAIL=...`.

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE actors "
        "ADD COLUMN is_platform_staff BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE actors DROP COLUMN is_platform_staff")
