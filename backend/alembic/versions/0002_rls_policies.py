"""RLS policies for tenant-scoped tables (per ADR-007).

Roles `app_user` and `alembic_migrator` are created by the docker-compose init
script (`infra/postgres/init/01-roles.sql`) so this migration assumes they exist.
The migration grants table-level privileges to `app_user` and enables RLS with
tenant-isolation policies referencing `current_setting('app.current_org', true)`.

`audit_log` has split policies: writes always allowed (the audit middleware sets
the right values), reads tenant-filtered with a compliance-officer escape hatch.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_TABLES = ("organisations", "projects", "org_policies")
NON_RLS_BUT_GRANTED = (
    "actors",
    "users",
    "oauth_identities",
    "agents",
    "services",
    "organisation_members",
    "audit_log",
    "capabilities",
    "org_policy_overrides",
    "api_keys",
)


def upgrade() -> None:
    # Grant baseline privileges so app_user can use the schema and tables.
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    for tbl in TENANT_TABLES + NON_RLS_BUT_GRANTED:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} TO app_user")
    # Future-proof: any new table created by this role gets the same grant.
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE alembic_migrator IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )

    # Tenant isolation on direct-org-scoped tables.
    for tbl in TENANT_TABLES:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")

    op.execute(
        """
        CREATE POLICY tenant_isolation ON organisations
          USING      (id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (id = current_setting('app.current_org', true)::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON projects
          USING      (organisation_id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid);
        """
    )
    op.execute(
        """
        CREATE POLICY tenant_isolation ON org_policies
          USING      (organisation_id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid);
        """
    )

    # audit_log: writes always allowed (middleware does the right thing); reads
    # tenant-filtered with compliance-officer escape (per ADR-007 amendment).
    op.execute("ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_write ON audit_log
          FOR INSERT
          WITH CHECK (TRUE);
        """
    )
    op.execute(
        """
        CREATE POLICY audit_tenant_read ON audit_log
          FOR SELECT
          USING (
            current_setting('app.role', true) = 'compliance_officer'
            OR organisation_id = current_setting('app.current_org', true)::uuid
          );
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_tenant_read ON audit_log")
    op.execute("DROP POLICY IF EXISTS audit_write ON audit_log")
    op.execute("ALTER TABLE audit_log NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_log DISABLE ROW LEVEL SECURITY")

    for tbl in TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {tbl}")
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")

    for tbl in TENANT_TABLES + NON_RLS_BUT_GRANTED:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE {tbl} FROM app_user")
    op.execute("REVOKE USAGE ON SCHEMA public FROM app_user")
    op.execute(
        "ALTER DEFAULT PRIVILEGES FOR ROLE alembic_migrator IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM app_user"
    )
