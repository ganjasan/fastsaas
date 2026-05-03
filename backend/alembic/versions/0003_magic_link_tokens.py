"""magic_link_tokens — single-table magic-link store with purpose discriminator.

Stores tokens for email verification, magic-link login, password reset, and org
invitations per ADR-008 §8c and identity-actor-and-auth design.md §D3.

- `token_hash` is the SHA-256 hex of the raw token; raw token only ever appears
  in the outbound email.
- `consumed_at` enforces single-use; partial index covers the common "find an
  unconsumed token for this actor + purpose" query.
- TTLs are app-side per ADR-008 §8c; we only store `expires_at` derived at mint.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE magic_link_tokens (
          token_hash    TEXT PRIMARY KEY,
          purpose       TEXT NOT NULL,
          actor_id      UUID NOT NULL REFERENCES actors(id) ON DELETE CASCADE,
          email         CITEXT NOT NULL,
          expires_at    TIMESTAMPTZ NOT NULL,
          consumed_at   TIMESTAMPTZ NULL,
          created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          CONSTRAINT magic_link_purpose_valid CHECK (
            purpose IN ('email_verification','magic_link_login','password_reset','org_invitation')
          )
        )
        """
    )
    op.execute(
        "CREATE INDEX magic_link_tokens_actor_purpose_idx "
        "ON magic_link_tokens (actor_id, purpose) "
        "WHERE consumed_at IS NULL"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE magic_link_tokens TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE magic_link_tokens")
