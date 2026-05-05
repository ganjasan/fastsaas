"""Extend role + operation + action CHECK constraints for the DPO bundle.

Companion to the audit-pii-scrub change (issue ganjasan/fastsaas#13).
The DPO bundle (Data Protection Officer) introduces:

- new role value `dpo` on `org_invitations.role` + `organisation_members.role`
- new operation value `scrub` on `capabilities.operation` (the new
  `Operation.SCRUB` capability gates the `audit_log` PII erasure path)
- new action value `scrub` on `audit_log.action` (the meta-audit row
  emitted by every wet scrub call records `action="scrub"` on a
  synthetic `entity_type="audit_scrub"` row, so the scrub itself is
  auditable)

Each of these tables ships a CHECK constraint enumerating the legal
values; this migration extends those enumerations rather than inflating
to a typed enum (TEXT + CHECK was the original choice in 0001 to keep
schema evolution cheap).

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-05

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE org_invitations DROP CONSTRAINT org_invitation_role_valid")
    op.execute(
        """
        ALTER TABLE org_invitations
        ADD CONSTRAINT org_invitation_role_valid
        CHECK (role IN ('admin','member','viewer','compliance_officer','dpo'))
        """
    )
    op.execute("ALTER TABLE organisation_members DROP CONSTRAINT org_member_role_valid")
    op.execute(
        """
        ALTER TABLE organisation_members
        ADD CONSTRAINT org_member_role_valid
        CHECK (role IN ('owner','admin','member','viewer','compliance_officer','dpo'))
        """
    )
    op.execute("ALTER TABLE capabilities DROP CONSTRAINT cap_operation_valid")
    op.execute(
        """
        ALTER TABLE capabilities
        ADD CONSTRAINT cap_operation_valid
        CHECK (operation IN ('read','write','delete','run','admin','share','grant','scrub'))
        """
    )
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_action_valid")
    op.execute(
        """
        ALTER TABLE audit_log
        ADD CONSTRAINT audit_action_valid
        CHECK (action IN ('create','update','delete','restore','scrub'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE audit_log DROP CONSTRAINT audit_action_valid")
    op.execute(
        """
        ALTER TABLE audit_log
        ADD CONSTRAINT audit_action_valid
        CHECK (action IN ('create','update','delete','restore'))
        """
    )
    op.execute("ALTER TABLE capabilities DROP CONSTRAINT cap_operation_valid")
    op.execute(
        """
        ALTER TABLE capabilities
        ADD CONSTRAINT cap_operation_valid
        CHECK (operation IN ('read','write','delete','run','admin','share','grant'))
        """
    )
    op.execute("ALTER TABLE organisation_members DROP CONSTRAINT org_member_role_valid")
    op.execute(
        """
        ALTER TABLE organisation_members
        ADD CONSTRAINT org_member_role_valid
        CHECK (role IN ('owner','admin','member','viewer','compliance_officer'))
        """
    )
    op.execute("ALTER TABLE org_invitations DROP CONSTRAINT org_invitation_role_valid")
    op.execute(
        """
        ALTER TABLE org_invitations
        ADD CONSTRAINT org_invitation_role_valid
        CHECK (role IN ('admin','member','viewer','compliance_officer'))
        """
    )
