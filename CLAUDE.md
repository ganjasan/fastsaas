# CLAUDE.md — FastSaaS

This file is loaded into context for every Claude Code session in this repo
and in any downstream project that inherits FastSaaS as a starter kit.
Read it before you write code.

## What FastSaaS is

A starter kit for SaaS products. Three foundation layers that downstream
business code stands on:

1. **Identity** — actors (HUMAN / AGENT / SERVICE per the CTI model in
   ADR-009), users, OAuth, magic links, JWT access + refresh.
   See `backend/src/fastsaas/identity/`.
2. **Tenancy + authorisation** — organisations, members, projects,
   invitations, project shares; capability primitive + role bundles
   per ADR-013; tenant isolation via Postgres RLS pinned on
   `app.current_org` per ADR-007.
   See `backend/src/fastsaas/tenants/` and `backend/src/fastsaas/authz/`.
3. **Audit** — `audit_log` table (immortal per ADR-006/010), explicit
   `record(...)` API + `AuditedModel` mixin, contextvar-propagated actor
   and intent. Every domain mutation produces a row in the same
   transaction. See `backend/src/fastsaas/audit/CLAUDE.md` for the full
   extension contract.

Your domain (scenarios, analyses, properties, model runs, …) sits **on
top** of these layers. The foundation does not know about your domain;
your domain inherits the foundation by convention.

## Architectural rules — must-not list

These are non-negotiable. A PR that violates one is wrong even if tests
pass.

- **No `Department` entity in the org hierarchy.** The hierarchy stays
  Org → Project. Decision #12 of the SaaS-core spike rescinded the
  three-level hierarchy. If a feature seems to need a department concept,
  re-read the spike's rationale before proposing a workaround.
- **`capability` is the only authz API.** Routes call `await can(...)`.
  No route ever runs `SELECT … FROM capabilities` directly. Bundles
  expand to capabilities in `authz/service.py` and stay opaque outside
  it.
- **`migrator_session_scope` only in the service layer.** Routes use
  `SessionDep` (the `app_user`-role session). The migrator (BYPASSRLS)
  session is reserved for service code that must operate before
  `app.current_org` is pinned (org bootstrap, invitation accept,
  cross-org reads).
- **`set_config(name, val, true)` to pin GUCs, not `SET LOCAL`.**
  asyncpg's prepared-statement cache loses `SET LOCAL` on reconnect; the
  function form survives.
- **Port shift `+100` (dev) / `+200` (test).** Postgres 5532 / 5632,
  Redis 6479 / 6579, Mailhog SMTP 1125/1225, Mailhog UI 8125/8225,
  backend 8100/—, vite 5273/—. CI standard.
- **Branch off `main` for every change.** No exceptions. The branch
  name should mirror the OpenSpec change slug (`feature/4-audit-trail-
  middleware` for change `audit-trail-middleware`).
- **Tests use GIVEN / WHEN / THEN docstrings.** Per `~/.claude/CLAUDE.md`
  — pattern is mandatory across the project.
- **Every domain mutation produces an audit row.** Either inherit
  `AuditedModel` and let the mixin handle CRUD, or call
  `await audit.record(db, ...)` explicitly inside the same transaction
  as the mutation. Skipping audit is the most expensive class of bug
  this codebase can ship.

## Where to look

- `requirements/decisions/` — Architecture Decision Records. ADR-006
  (PKs + cascade), ADR-007 (multi-tenant isolation), ADR-009 (actor
  CTI model), ADR-010 (audit log shape), ADR-013 (capabilities + role
  bundles), ADR-016 (org policies + overrides), ADR-017 (API keys).
- `requirements/formal/use-cases/` — Wiegers-style use cases. UC-001
  through UC-010.
- `requirements/formal/stakeholders/` — Stakeholder profiles. The
  Compliance Officer profile (`SH-compliance-officer.md`) is the
  primary consumer of `audit_log` reads.
- `openspec/changes/` — active change packages. Each contains
  `proposal.md`, `design.md`, `tasks.md`, and `specs/<area>/spec.md`
  with ADDED / MODIFIED requirements.
- `openspec/specs/` — current capability specs (synced when changes
  archive).
- `backend/src/fastsaas/<module>/CLAUDE.md` — module-level guides where
  the contract is non-trivial. Always present for `audit/`.

## Recipes

These are copy-paste templates for the most common things you will be
asked to do. Fill in the blanks; don't refactor without reason.

### Add a tenant-scoped table

```python
# backend/src/fastsaas/<your_domain>/models.py
from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field

from fastsaas.audit import AuditedModel


class Scenario(AuditedModel, table=True):
    __tablename__ = "scenarios"
    __audit_entity_type__: ClassVar[str] = "scenario"
    # __audit_redact__: ClassVar[frozenset[str]] = frozenset({"private_field"})

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
    created_at: datetime = Field(
        sa_column=Column(
            DateTime(timezone=True), nullable=False, server_default=text("NOW()")
        )
    )
    deleted_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
```

Then add a migration that creates the table AND turns on RLS pinned on
`app.current_org` (see `0002_rls_policies.py` for the pattern).

### Add a route gated by a capability

```python
@router.post("/orgs/{slug}/scenarios")
async def create_scenario(
    body: ScenarioCreateRequest,
    ctx: TenantContextDep,
    db: SessionDep,
) -> ScenarioRead:
    ok = await can(
        ctx.actor.actor_id,
        Operation.WRITE,
        ResourceType.PROJECT,  # or another resource_type as appropriate
        ctx.organisation.id,
        db=db,
        cache=get_redis(),
    )
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail={"code": "authz.forbidden"})

    scenario = await ScenarioService.create(...)
    return ScenarioRead.model_validate(scenario)
```

### Add a service method that audits

```python
class ScenarioService:
    @staticmethod
    async def create(*, org_id: UUID, name: str, created_by: UUID) -> Scenario:
        async with migrator_session_scope() as db:
            scenario = Scenario(organisation_id=org_id, name=name)
            db.add(scenario)
            await db.flush()
            await db.refresh(scenario)
            # AuditedModel mixin already emitted the row via after_insert
            # listener — no explicit record() needed for plain CRUD.
            return scenario
```

For non-CRUD operations (mass-revoke, fan-out, soft-delete with cascade),
call `audit.record(...)` explicitly — see `audit/CLAUDE.md`.

### Add a vitest case (frontend)

```ts
// frontend/src/<feature>/<feature>.test.tsx
import { describe, it, expect } from "vitest";

describe("<feature>", () => {
  it("does <something> WHEN <input> GIVEN <setup>", () => {
    // GIVEN ...
    // WHEN ...
    // THEN ...
    expect(...).toBe(...);
  });
});
```

### Add a Playwright e2e step

E2E lives under `e2e/` (issue #7). Use the existing dev-bypass login
helper rather than rolling new credentials per spec.

## Module-level guides

When the contract is non-obvious, modules ship their own `CLAUDE.md`.
Always read these before extending the module:

- `backend/src/fastsaas/audit/CLAUDE.md` — audit core extension contract,
  decision tree (mixin vs explicit), recipes for downstream entities and
  non-CRUD operations, what NOT to do.
