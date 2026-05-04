"""project_shares — UC-001 per-project guest invitations.

Distinct from `org_invitations` because the semantics differ: a project
share grants a single `read:project` capability scoped to one project_id,
without creating an `organisation_members` row. Guests cannot list other
projects, members, or invitations in the org.

Token model mirrors org_invitations: 32-byte URL-safe random,
`sha256(token)` at rest, single-use via `consumed_at`. TTL configurable
per share at mint time (default 14 days; capped to 30 in service code).

RLS:
- `tenant_isolation` on `organisation_id` so the admin members page can
  list pending shares for the pinned org.

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE project_shares (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          project_id       UUID NOT NULL REFERENCES projects(id),
          organisation_id  UUID NOT NULL REFERENCES organisations(id),
          email            CITEXT NOT NULL,
          token_hash       TEXT NOT NULL UNIQUE,
          shared_by        UUID NOT NULL REFERENCES actors(id),
          expires_at       TIMESTAMPTZ NOT NULL,
          consumed_at      TIMESTAMPTZ NULL,
          consumed_by      UUID NULL REFERENCES actors(id),
          consumed_capability_id UUID NULL REFERENCES capabilities(id),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_project_shares_project "
        "ON project_shares (project_id) "
        "WHERE consumed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_project_shares_email "
        "ON project_shares (email) "
        "WHERE consumed_at IS NULL"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE project_shares TO app_user")

    op.execute("ALTER TABLE project_shares ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_shares FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON project_shares
          USING      (organisation_id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON project_shares")
    op.execute("ALTER TABLE project_shares NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE project_shares DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE project_shares FROM app_user")
    op.execute("DROP INDEX IF EXISTS idx_project_shares_email")
    op.execute("DROP INDEX IF EXISTS idx_project_shares_project")
    op.execute("DROP TABLE IF EXISTS project_shares")
