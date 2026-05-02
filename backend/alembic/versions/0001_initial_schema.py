"""Initial SaaS-core schema (full set per platform-saas-core-architecture-spike).

Creates every table decided in the spike so subsequent sub-issues add
behaviour without further migrations:
- CTI actor model (per ADR-009 + amendment): actors, users, oauth_identities,
  agents, services.
- Tenant primitives (per ADR-006, post-Decision-#12-rescission): organisations,
  organisation_members, projects.
- Audit log (per ADR-010): audit_log.
- Authorization (per ADR-013): capabilities.
- Org policies (per ADR-016): org_policies, org_policy_overrides.
- API keys (per ADR-017): api_keys.

UUID v7 PKs are app-generated (per ADR-006); a `gen_random_uuid()` default is
provided as a fallback so tests / direct SQL inserts work without an explicit id.

asyncpg requires single-statement prepared queries — every op.execute() below
contains exactly one SQL statement.

Revision ID: 0001
Revises:
Create Date: 2026-05-01

"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _exec_each(*statements: str) -> None:
    """Execute each SQL statement individually (asyncpg restriction)."""
    for stmt in statements:
        op.execute(stmt)


def upgrade() -> None:
    # `citext` extension is installed by the postgres init script
    # (infra/postgres/init/01-roles.sql) so the migration role doesn't need
    # SUPERUSER. The IF NOT EXISTS guard keeps this safe to re-run against a
    # stripped-down DB where it may be missing.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    # --------------------------------------------------------------- actors (CTI)
    _exec_each(
        """
        CREATE TABLE actors (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_type      TEXT NOT NULL,
          parent_actor_id UUID NULL REFERENCES actors(id),
          display_name    TEXT NOT NULL,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          deleted_at      TIMESTAMPTZ NULL,
          CONSTRAINT actor_type_valid    CHECK (actor_type IN ('HUMAN','AGENT','SERVICE')),
          CONSTRAINT agent_has_parent    CHECK (actor_type <> 'AGENT'   OR parent_actor_id IS NOT NULL),
          CONSTRAINT human_no_parent     CHECK (actor_type <> 'HUMAN'   OR parent_actor_id IS NULL),
          CONSTRAINT service_no_parent   CHECK (actor_type <> 'SERVICE' OR parent_actor_id IS NULL)
        )
        """,
        "CREATE INDEX idx_actors_type   ON actors (actor_type)      WHERE deleted_at IS NULL",
        "CREATE INDEX idx_actors_parent ON actors (parent_actor_id) WHERE deleted_at IS NULL AND parent_actor_id IS NOT NULL",
    )

    op.execute(
        """
        CREATE TABLE users (
          actor_id        UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
          email           CITEXT UNIQUE NOT NULL,
          password_hash   TEXT NULL,
          email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
          locale          TEXT NOT NULL DEFAULT 'en',
          timezone        TEXT NOT NULL DEFAULT 'UTC',
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    _exec_each(
        """
        CREATE TABLE oauth_identities (
          user_actor_id   UUID NOT NULL REFERENCES users(actor_id) ON DELETE CASCADE,
          provider        TEXT NOT NULL,
          provider_uid    TEXT NOT NULL,
          PRIMARY KEY (provider, provider_uid)
        )
        """,
        "CREATE INDEX idx_oauth_user ON oauth_identities (user_actor_id)",
    )

    op.execute(
        """
        CREATE TABLE agents (
          actor_id        UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
          allowed_scopes  TEXT[] NOT NULL DEFAULT '{}',
          created_via     TEXT NOT NULL,
          last_used_at    TIMESTAMPTZ NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE services (
          actor_id          UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
          organisation_id   UUID NOT NULL,
          owner_actor_id    UUID NOT NULL REFERENCES actors(id),
          description       TEXT,
          last_used_at      TIMESTAMPTZ NULL
        )
        """
    )

    # --------------------------------------------------------------- tenants
    _exec_each(
        """
        CREATE TABLE organisations (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          name            TEXT NOT NULL,
          theme           JSONB NOT NULL DEFAULT '{}'::jsonb,
          quota           JSONB NOT NULL DEFAULT '{}'::jsonb,
          created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          deleted_at      TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX idx_orgs_active ON organisations (id) WHERE deleted_at IS NULL",
    )

    op.execute(
        """
        ALTER TABLE services
          ADD CONSTRAINT services_organisation_fk
          FOREIGN KEY (organisation_id) REFERENCES organisations(id)
        """
    )

    _exec_each(
        """
        CREATE TABLE organisation_members (
          organisation_id  UUID NOT NULL REFERENCES organisations(id),
          actor_id         UUID NOT NULL REFERENCES actors(id),
          role             TEXT NOT NULL,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          PRIMARY KEY (organisation_id, actor_id),
          CONSTRAINT org_member_role_valid CHECK (role IN ('owner','admin','member','viewer','compliance_officer'))
        )
        """,
        "CREATE INDEX idx_org_members_actor ON organisation_members (actor_id)",
    )

    _exec_each(
        """
        CREATE TABLE projects (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          organisation_id  UUID NOT NULL REFERENCES organisations(id),
          name             TEXT NOT NULL,
          description      TEXT,
          created_by       UUID NOT NULL REFERENCES actors(id),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          deleted_at       TIMESTAMPTZ NULL
        )
        """,
        "CREATE INDEX idx_projects_org ON projects (organisation_id) WHERE deleted_at IS NULL",
    )

    # --------------------------------------------------------------- audit
    _exec_each(
        """
        CREATE TABLE audit_log (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          timestamp        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          actor_id         UUID NOT NULL REFERENCES actors(id),
          actor_type       TEXT NOT NULL,
          parent_actor_id  UUID NULL,
          organisation_id  UUID NULL,
          intent_hash      TEXT NOT NULL,
          entity_type      TEXT NOT NULL,
          entity_id        UUID NOT NULL,
          action           TEXT NOT NULL,
          diff             JSONB NOT NULL,
          intent_metadata  JSONB NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT audit_action_valid CHECK (action IN ('create','update','delete','restore'))
        )
        """,
        "CREATE INDEX idx_audit_org_entity_time ON audit_log (organisation_id, entity_type, entity_id, timestamp DESC)",
        "CREATE INDEX idx_audit_intent_hash     ON audit_log (intent_hash)",
        "CREATE INDEX idx_audit_actor_time      ON audit_log (actor_id, timestamp DESC)",
        "CREATE INDEX idx_audit_timestamp       ON audit_log (timestamp DESC)",
    )

    # --------------------------------------------------------------- capabilities
    _exec_each(
        """
        CREATE TABLE capabilities (
          id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_id        UUID NOT NULL REFERENCES actors(id),
          operation       TEXT NOT NULL,
          resource_type   TEXT NOT NULL,
          resource_id     UUID NULL,
          conditions      JSONB NOT NULL DEFAULT '{}'::jsonb,
          bundle_name     TEXT NULL,
          granted_by      UUID REFERENCES actors(id),
          granted_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          expires_at      TIMESTAMPTZ NULL,
          revoked_at      TIMESTAMPTZ NULL,
          policy_blocked  BOOLEAN NOT NULL DEFAULT FALSE,
          metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT cap_operation_valid     CHECK (operation IN ('read','write','delete','run','admin','share','grant')),
          CONSTRAINT cap_resource_type_valid CHECK (resource_type IN ('organisation','project','scenario','audit_log','agent','service','*'))
        )
        """,
        """
        CREATE INDEX idx_cap_lookup
          ON capabilities (actor_id, operation, resource_type, resource_id)
          WHERE revoked_at IS NULL AND policy_blocked = FALSE
        """,
        """
        CREATE INDEX idx_cap_bundle
          ON capabilities (actor_id, bundle_name)
          WHERE revoked_at IS NULL
        """,
    )

    # --------------------------------------------------------------- org policies
    _exec_each(
        """
        CREATE TABLE org_policies (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          organisation_id  UUID NOT NULL REFERENCES organisations(id),
          name             TEXT NOT NULL,
          description      TEXT,
          rule_json        JSONB NOT NULL,
          priority         INT NOT NULL DEFAULT 100,
          enabled          BOOLEAN NOT NULL DEFAULT TRUE,
          created_by       UUID NOT NULL REFERENCES actors(id),
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          deleted_at       TIMESTAMPTZ NULL,
          UNIQUE (organisation_id, name)
        )
        """,
        "CREATE INDEX idx_org_policies_org ON org_policies (organisation_id) WHERE deleted_at IS NULL AND enabled = TRUE",
    )

    _exec_each(
        """
        CREATE TABLE org_policy_overrides (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          policy_id        UUID NOT NULL REFERENCES org_policies(id),
          granted_by       UUID NOT NULL REFERENCES actors(id),
          reason           TEXT NOT NULL,
          expires_at       TIMESTAMPTZ NOT NULL,
          created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # NB: Postgres requires IMMUTABLE functions in index predicates, so we
        # cannot use `WHERE expires_at > NOW()`. The plain (policy_id, expires_at)
        # composite index is enough — query side filters by NOW() at lookup time
        # and the planner can use the index for both columns.
        "CREATE INDEX idx_policy_overrides_active ON org_policy_overrides (policy_id, expires_at)",
    )

    # --------------------------------------------------------------- api keys
    _exec_each(
        """
        CREATE TABLE api_keys (
          id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          actor_id              UUID NOT NULL REFERENCES actors(id),
          key_hash              TEXT NOT NULL,
          key_prefix            TEXT NOT NULL,
          name                  TEXT NOT NULL,
          scope_restriction     JSONB NULL,
          created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          created_by            UUID NOT NULL REFERENCES actors(id),
          last_used_at          TIMESTAMPTZ NULL,
          last_used_ip          INET NULL,
          expires_at            TIMESTAMPTZ NULL,
          revoked_at            TIMESTAMPTZ NULL,
          revoked_by            UUID REFERENCES actors(id),
          revoked_reason        TEXT NULL,
          rotation_grace_until  TIMESTAMPTZ NULL,
          metadata              JSONB NOT NULL DEFAULT '{}'::jsonb
        )
        """,
        "CREATE UNIQUE INDEX idx_keys_hash ON api_keys (key_hash) WHERE revoked_at IS NULL",
        "CREATE INDEX idx_keys_actor       ON api_keys (actor_id)  WHERE revoked_at IS NULL",
        "CREATE INDEX idx_keys_prefix      ON api_keys (key_prefix)",
    )


def downgrade() -> None:
    for tbl in (
        "api_keys",
        "org_policy_overrides",
        "org_policies",
        "capabilities",
        "audit_log",
        "projects",
        "organisation_members",
        "services",
        "agents",
        "oauth_identities",
        "users",
        "organisations",
        "actors",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
