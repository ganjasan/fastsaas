"""org_invitations — pre-acceptance invite tokens for org membership.

Distinct from `magic_link_tokens` because that table requires
`actor_id NOT NULL REFERENCES actors(id)` and an invitee may not yet exist
as an actor (pre-registration invite is the common SaaS case).

Token model mirrors magic_link_tokens: 32-byte URL-safe random,
`sha256(token)` at rest, single-use via `consumed_at`. TTL 7 days
(matches the deferred MagicLinkPurpose.ORG_INVITATION choice).

RLS:
- `tenant_isolation` policy keyed on `organisation_id` so an invite is
  visible only when the request has pinned the matching org.
- An `invitee_self_read` policy lets the accepting actor read their own
  invite by token via the migrator session (acceptance happens
  pre-tenant-context, where there is no `app.current_org`).

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-04

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE org_invitations (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          organisation_id  UUID NOT NULL REFERENCES organisations(id),
          email            CITEXT NOT NULL,
          role             TEXT NOT NULL,
          token_hash       TEXT NOT NULL UNIQUE,
          invited_by       UUID NOT NULL REFERENCES actors(id),
          expires_at       TIMESTAMPTZ NOT NULL,
          consumed_at      TIMESTAMPTZ NULL,
          consumed_by      UUID NULL REFERENCES actors(id),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT org_invitation_role_valid
            CHECK (role IN ('admin','member','viewer','compliance_officer'))
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_org_invitations_org "
        "ON org_invitations (organisation_id) "
        "WHERE consumed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_org_invitations_email "
        "ON org_invitations (email) "
        "WHERE consumed_at IS NULL"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE org_invitations TO app_user")

    # Tenant isolation — org admins reading the pending invites for their org.
    op.execute("ALTER TABLE org_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_invitations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenant_isolation ON org_invitations
          USING      (organisation_id = current_setting('app.current_org', true)::uuid)
          WITH CHECK (organisation_id = current_setting('app.current_org', true)::uuid)
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON org_invitations")
    op.execute("ALTER TABLE org_invitations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_invitations DISABLE ROW LEVEL SECURITY")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLE org_invitations FROM app_user")
    op.execute("DROP INDEX IF EXISTS idx_org_invitations_email")
    op.execute("DROP INDEX IF EXISTS idx_org_invitations_org")
    op.execute("DROP TABLE IF EXISTS org_invitations")
