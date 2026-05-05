# CLAUDE.md — `audit/`

This module is FastSaaS's third foundation layer. Every domain mutation in
the platform — core or downstream — must produce an `audit_log` row, in the
same transaction. This file is the contract every PR that touches a
mutation has to honour.

Read ADR-010 (Audit log shape, including the 2026-05-04 amendment
"Extension contract for downstream products") before changing anything in
this directory.

## Decision tree — explicit `record(...)` vs `AuditedModel`

```
Are you mutating exactly one ORM entity that maps to one DB row?
├── Yes → AuditedModel. Inherit it, set __audit_entity_type__, you're done.
│         The mixin's mapper-event listener emits the audit row inside the
│         caller's transaction.
└── No  → Explicit record().
          Mass-revoke, capability fan-out, soft-delete-with-cascade,
          policy denial logged from can(), or any operation whose
          intent is not "write one row" — call audit.record(...) at
          the boundary where the intent is clear.
```

The two are complementary, not redundant. The mixin can't see "I just
revoked 47 capability rows by `metadata.org_id` filter". Explicit
`record(...)` can't be slotted into a downstream `class Scenario(SQLModel,
table=True)` without changing every CRUD function.

## Recipe — add a downstream audited entity

```python
# In your downstream package (e.g. apps/<your-saas>/src/<pkg>/models.py)
from typing import ClassVar
from uuid import UUID

from fastsaas.audit import AuditedModel
from sqlalchemy import Column, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field


class Scenario(AuditedModel, table=True):
    __tablename__ = "scenarios"
    __audit_entity_type__: ClassVar[str] = "scenario"  # lowercase, singular, noun
    # __audit_redact__: ClassVar[frozenset[str]] = frozenset({"private_field"})
    # __audit_skip__: ClassVar[bool] = True  # for caches / scratch only

    id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True),
            primary_key=True,
            server_default=text("gen_random_uuid()"),
        )
    )
    organisation_id: UUID = Field(
        sa_column=Column(
            PG_UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False
        )
    )
    name: str = Field(sa_column=Column(String, nullable=False))
```

That's it. Insert / update / delete on this class will produce
`audit_log` rows with `entity_type = "scenario"`, the right action, the
right diff, and the redaction step applied — provided the request's
`actor_var` and `intent_var` were set by `AuditContextMiddleware`
(automatic for all HTTP requests).

### `entity_type` naming convention

`audit_log.entity_type` is `TEXT` with no DB CHECK. Convention enforced
by code review:

- **lowercase, singular, noun**: `scenario`, `analysis`, `property`,
  `model_run`. NOT `Scenarios`, `created_scenario`, `Scenario_v2`.
- **Reserved core values** — do NOT shadow:
  `organisation`, `project`, `member`, `share`, `org_invitation`,
  `capability`, `user`, `actor`.

If a downstream wants `share` it has to pick a different name (`asset_share`,
`scenario_share`). Filter queries are then uniform across core and
downstream:

```sql
SELECT * FROM audit_log
WHERE organisation_id = $1
  AND entity_type IN ('project', 'scenario');
```

## Recipe — audit a non-CRUD service operation

```python
from fastsaas import audit

async def revoke_org_wide_keys(*, org_id: UUID, revoked_by: UUID) -> int:
    async with migrator_session_scope() as db:
        result = await db.execute(
            update(ApiKey)
            .where(ApiKey.organisation_id == org_id, ApiKey.revoked_at.is_(None))
            .values(revoked_at=now(), revoked_by=revoked_by)
            .returning(ApiKey.id)
        )
        ids = [row for row in result.scalars().all()]
        for key_id in ids:
            await audit.record(
                db,
                action="delete",
                entity_type="api_key",
                entity_id=key_id,
                diff={
                    "before": {"revoked_at": None},
                    "after": {"revoked_at": now().isoformat(), "revoked_by": str(revoked_by)},
                },
                organisation_id=org_id,
                extra_intent_metadata={
                    "org_id": str(org_id),
                    "revoke_reason": "org_wide_rotation",
                },
            )
        return len(ids)
```

Things to notice:

- `record(...)` is called inside the existing `migrator_session_scope` —
  the audit row commits with the mutation, or rolls back together.
- `actor` and `intent_hash` are read from contextvars by default; pass
  them explicitly only if you're outside a request (worker, script).
- `extra_intent_metadata` is for free-form provenance — `org_id`,
  `project_id`, `revoke_reason`, anything that helps the compliance
  officer reconstruct the timeline.
- Sensitive fields are stripped from `diff` before insert via
  `GLOBAL_REDACT`. If your model carries domain-specific secrets, pass
  `extra_redact={"my_secret_field"}` or declare `__audit_redact__` on
  the model.

## Sensitive-field redaction

Two layers — both extend, neither replaces:

1. **Global denylist** (`audit/redact.py`):
   `{password_hash, token_hash, api_key_hash, key_hash, client_secret, raw_token}`.
   New PRs that add sensitive columns MUST extend this set.
2. **Per-model**: `__audit_redact__: ClassVar[frozenset[str]]` on an
   `AuditedModel` subclass.
3. **Per-call**: `record(..., extra_redact={"my_field"})`.

Redacted keys appear in the stored diff as `"<redacted>"`. The literal,
not omission — presence-of-key is itself signal ("this revision had a
secret field of this name").

## Reading `audit_log`

RLS lives in migration `0002_rls_policies.py`:

```sql
-- Default — every read is org-scoped on app.current_org
CREATE POLICY audit_tenant_read ON audit_log FOR SELECT
USING (organisation_id = current_setting('app.current_org', true)::uuid);

-- Compliance-officer escape — `app.role` GUC opens cross-org reads
CREATE POLICY audit_compliance_read ON audit_log FOR SELECT
USING (current_setting('app.role', true) = 'compliance_officer');
```

To read as a compliance officer:

```python
async with session_scope() as db:
    await db.execute(
        text("SELECT set_config('app.role', 'compliance_officer', true)")
    )
    rows = (
        await db.execute(
            text(
                "SELECT entity_type, entity_id, action, intent_hash, diff "
                "FROM audit_log "
                "WHERE timestamp >= :since "
                "ORDER BY timestamp DESC LIMIT 1000"
            ),
            {"since": since},
        )
    ).all()
```

The compliance-officer GUC is honoured only inside the `app_user` role's
RLS context; the migrator (`BYPASSRLS`) sees everything regardless.
Routes that expose audit reads MUST gate on the
`role:compliance_officer` capability before pinning the GUC — the GUC
itself is not authentication.

### Untrusted strings on the read side

`intent_metadata.original_prompt`, `intent_metadata.user_agent`, and
`intent_metadata.path` contain client-controlled values straight from the
request. JSON encoding by Pydantic / asyncpg keeps them safe in API
responses, but read-side renderers (admin UI, PDF report exports, Slack
notifications) MUST treat these fields as untrusted strings and escape
them appropriately for their output context. Never interpolate them into
HTML, shell commands, or LLM prompts without escaping. Length is bounded
to 4096 chars at write time (`audit/intent.py::_bounded`), but content
is verbatim — assume malicious payloads.

## What NOT to do

- **Do NOT bypass `record(...)` with raw SQL writes to domain tables.**
  Raw `INSERT INTO scenarios ...` from a route or migration produces no
  audit row — silent coverage gap. If you must run raw SQL, call
  `record(...)` immediately after with the equivalent diff.
- **Do NOT reuse a core `entity_type` for a downstream concept.**
  `share` is reserved by FastSaaS. Picking it for an unrelated
  downstream feature collides every report query that filters on
  `WHERE entity_type = 'share'`.
- **Do NOT strip `intent_metadata` to "save space".** The compliance
  officer's investigation depends on `request_id`, `ip`, `user_agent`,
  and `original_prompt`. Disk is cheap; provenance is not.
- **Do NOT mutate `audit_log` rows after the fact.** The table is
  immortal per ADR-006; RLS has no UPDATE/DELETE policies for the app
  role. If GDPR scrubbing is needed, use the dedicated PII-redaction
  endpoint (backlog) — it preserves the structural trail and only
  zeroes fields inside `intent_metadata`.
- **Do NOT add a custom `entity_type` like `widget_v2` for migrations.**
  Schema versions belong in `intent_metadata.schema_version` if at all.
- **Do NOT silently skip audit on operations that "feel internal".**
  Background jobs, scheduled cleanups, and re-orgs all touch domain
  rows the compliance officer is auditing. Set `actor_var` from the
  worker harness and call `record(...)` like any other code path.

## Failure mode — silent coverage gap

If a downstream developer ships a new SQLModel `table=True` class
without inheriting `AuditedModel` and without explicit `record(...)`
calls, audit rows are silently absent — there is no compile-time signal
of "you forgot audit". Mitigations:

- This file is loaded into context for every Claude Code session in
  this repo or its forks.
- ADR-010 amendment formalises the contract.
- A CI check that warns when a new `table=True` class doesn't inherit
  `AuditedModel` and isn't on an explicit allowlist is tracked as
  backlog (would close the gap mechanically).

If you're shipping a new downstream domain table and Claude isn't sure
whether to add `AuditedModel`: the answer is **yes, add it**. Opt-out
via `__audit_skip__ = True` only for caches and scratch tables — never
for user-facing data.
