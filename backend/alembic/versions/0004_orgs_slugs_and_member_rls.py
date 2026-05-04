"""Slugs on orgs/projects + RLS on organisation_members and capabilities.

0001 created the four tables; 0002 wrapped `organisations`, `projects`,
`org_policies`, and `audit_log` with RLS. This revision adds:

- `organisations.slug CITEXT NOT NULL UNIQUE` (URL-safe, regex-checked).
- `projects.slug CITEXT NOT NULL` with `UNIQUE (organisation_id, slug)`.
- RLS `tenant_isolation` policy on `organisation_members`.
- RLS on `capabilities`:
    * `actor_self_read` — actor always sees their own capability rows
      (uses `app.current_actor`, set by tenant-context middleware).
    * `org_admin_scope` — capabilities matching `metadata->>'org_id' =
      app.current_org` are visible (admin / member listings).
    * `app_writes` / `app_updates` — application services mint and revoke;
      route handlers go through `mint_*`/`revoke_*` only.

`fastsaas` is pre-launch (no production data) so the slug additions are
safe in one revision — no backfill required.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-03

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ----------------------------------------------------------- organisations.slug
    op.execute("ALTER TABLE organisations ADD COLUMN slug CITEXT NOT NULL")
    op.execute(
        "ALTER TABLE organisations "
        "ADD CONSTRAINT org_slug_format CHECK (slug ~ '^[a-z0-9-]{3,63}$')"
    )
    op.execute("CREATE UNIQUE INDEX idx_orgs_slug ON organisations (slug)")

    # ----------------------------------------------------------- projects.slug
    op.execute("ALTER TABLE projects ADD COLUMN slug CITEXT NOT NULL")
    op.execute(
        "ALTER TABLE projects "
        "ADD CONSTRAINT project_slug_format CHECK (slug ~ '^[a-z0-9-]{3,63}$')"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_projects_org_slug ON projects (organisation_id, slug)"
    )

    # ----------------------------------------------------------- RLS: organisation_members
    op.execute("ALTER TABLE organisation_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organisation_members FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON organisation_members
          USING      (organisation_id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid)
        """
    )

    # ----------------------------------------------------------- RLS: capabilities
    op.execute("ALTER TABLE capabilities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE capabilities FORCE ROW LEVEL SECURITY")
    # An actor always sees their own capability rows, regardless of pinned org.
    # `app.current_actor` is set by the tenant-context middleware after
    # `current_actor` resolves the JWT.
    op.execute(
        """
        CREATE POLICY actor_self_read ON capabilities
          FOR SELECT
          USING (actor_id = current_setting('app.current_actor', true)::uuid)
        """
    )
    # Admins listing capabilities granted within the pinned org. `metadata.org_id`
    # is set by `mint_bundle` / `mint_capability`.
    op.execute(
        """
        CREATE POLICY org_admin_scope ON capabilities
          FOR SELECT
          USING (metadata->>'org_id' = current_setting('app.current_org', true))
        """
    )
    # Mutations are always allowed at the DB layer; the application's
    # mint_*/revoke_* services are the only callers and gate access via
    # `can(...)` before they run.
    op.execute(
        """
        CREATE POLICY app_writes ON capabilities
          FOR INSERT
          WITH CHECK (TRUE)
        """
    )
    op.execute(
        """
        CREATE POLICY app_updates ON capabilities
          FOR UPDATE
          USING (TRUE)
        """
    )


def downgrade() -> None:
    # capabilities RLS
    op.execute("DROP POLICY IF EXISTS app_updates       ON capabilities")
    op.execute("DROP POLICY IF EXISTS app_writes        ON capabilities")
    op.execute("DROP POLICY IF EXISTS org_admin_scope   ON capabilities")
    op.execute("DROP POLICY IF EXISTS actor_self_read   ON capabilities")
    op.execute("ALTER TABLE capabilities NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE capabilities DISABLE ROW LEVEL SECURITY")

    # organisation_members RLS
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON organisation_members")
    op.execute("ALTER TABLE organisation_members NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organisation_members DISABLE ROW LEVEL SECURITY")

    # projects.slug
    op.execute("DROP INDEX IF EXISTS idx_projects_org_slug")
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS project_slug_format")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS slug")

    # organisations.slug
    op.execute("DROP INDEX IF EXISTS idx_orgs_slug")
    op.execute("ALTER TABLE organisations DROP CONSTRAINT IF EXISTS org_slug_format")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS slug")
