---
title: Audit trail middleware — design
status: draft
linked_issue: ganjasan/fastsaas#4
created: 2026-05-04
traces_to:
  adr:
    - ADR-010
    - ADR-007
    - ADR-013
---

# Design

## Context

`audit_log` was created in migration 0001 with the schema ADR-010 chose: `id, timestamp, actor_id, actor_type, parent_actor_id, organisation_id, intent_hash, entity_type, entity_id, action, diff, intent_metadata`. RLS in migration 0002 lets compliance officers read cross-org via `BYPASSRLS` while everyday tenant reads are scoped on `app.current_org`. The write side has not been wired.

Two pressures shape this design:

1. **Compliance must be cheap.** Forgetting to write an audit row on a new mutation must be hard. Default outcome should be "the row gets written"; opt-out should be deliberate.
2. **Foundation must be cheap.** Downstream products (FASTSAAS-app and friends) own their own domain tables — `scenarios`, `analyses`, `properties`, etc. They must not have to fork or patch FastSaaS to add audit; they should pick it up by convention. This is in addition to (1) — the same primitive should serve core *and* downstream identically.

Two extension styles cover the realistic surface:

- **Explicit `record(...)`** — for operations that aren't a single ORM mutation (mass-revoke, capability fan-out, soft-delete-with-cascade, hand-rolled actions). Service layer calls `await audit.record(db, …)` inside its existing `migrator_session_scope` transaction. Maximum control over `diff` and `intent_metadata`.
- **`AuditedModel` mixin** — for typical CRUD entities. Inheritance flips on SQLAlchemy mapper-event listeners that compute `diff` from attribute history and call `record(...)` automatically. Maximum convenience for downstream domain tables.

The two are complementary, not redundant: the mixin can't see "I just revoked 47 capability rows by `metadata.org_id` filter"; explicit `record(...)` can't be slotted into a downstream `class Scenario(SQLModel, table=True)` without changing every CRUD function.

## D1. Schema (no migration)

`audit_log` already exists from migration 0001. No schema change. New ORM mirror in `audit/models.py`:

```python
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"
    id: UUID                    # PK, server gen_random_uuid
    timestamp: datetime          # NOW() default
    actor_id: UUID               # FK actors.id
    actor_type: ActorType        # denormalised
    parent_actor_id: UUID | None # AGENT-initiator denorm
    organisation_id: UUID | None # nullable for org-deleted-survives invariant
    intent_hash: str             # prefixed: idem:|agent:|sess:|req:
    entity_type: str             # OPEN VOCABULARY — see §D6
    entity_id: UUID
    action: str                  # 'create' | 'update' | 'delete' | 'restore'
    diff: dict[str, Any]         # {before: {...}, after: {...}}
    intent_metadata: dict[str, Any]  # {request_id, ip, ua, original_prompt, ...}
```

ORM is for **reads** (future compliance UI, tests). All writes go through `service.record(...)`.

## D2. The two extension styles

### Style A — Explicit `record(...)`

```python
# audit/service.py
async def record(
    db: AsyncSession,
    *,
    action: Literal["create", "update", "delete", "restore"],
    entity_type: str,
    entity_id: UUID,
    diff: dict[str, Any],
    actor: CurrentActor | None = None,        # default: actor_var.get()
    organisation_id: UUID | None = None,      # default: derived from session GUC
    extra_intent_metadata: dict[str, Any] | None = None,
    intent_hash: str | None = None,           # default: intent_var.get()
) -> AuditLog:
    """Append an audit row. Runs inside the caller's open transaction."""
```

Call sites — every core service-layer mutation. The redaction step (§D5) runs on `diff` before insert.

### Style B — `AuditedModel` mixin

```python
# audit/mixin.py
class AuditedModel(SQLModel):
    """Inherit and (optionally) declare:
        __audit_entity_type__: str           # default: tablename singular
        __audit_redact__: ClassVar[set[str]] # default: empty; merged with global denylist
        __audit_skip__: ClassVar[bool]       # opt-out, defaults False
    """
    __audit_entity_type__: ClassVar[str | None] = None
    __audit_redact__: ClassVar[set[str]] = frozenset()
    __audit_skip__: ClassVar[bool] = False
```

Module-import side-effect registers SQLAlchemy mapper events for every subclass:

```python
# audit/mixin.py — on import
@event.listens_for(AuditedModel, "after_insert", propagate=True)
def _on_insert(mapper, connection, target): ...    # action="create"
@event.listens_for(AuditedModel, "after_update", propagate=True)
def _on_update(mapper, connection, target): ...    # action="update" (or "delete" if soft-delete column flips)
@event.listens_for(AuditedModel, "after_delete", propagate=True)
def _on_delete(mapper, connection, target): ...    # action="delete"
```

Inside the listener:

1. Pull `actor` and `intent` from contextvars (§D3).
2. Build `diff` via `inspect(target).attrs.<col>.history` — only changed columns; soft-delete-flip detected by `deleted_at IS NULL → NOT NULL` (then action = "delete" not "update").
3. Apply redaction (§D5).
4. Synchronously emit an `INSERT INTO audit_log` via the same `connection` so it joins the caller's transaction.

Soft-delete on FastSaaS uses a `deleted_at` column convention; the listener watches for that specific transition to choose `action="delete"` over `action="update"` when only that column flips.

### When to use which

- **CRUD on a single ORM entity → mixin.** Inherit, you're done.
- **Mass-revoke / fan-out / cross-row → explicit.** The mixin can't see the intent, only the per-row mutation.
- **Non-DB events** (e.g. policy denial logged from `can()`) → explicit, with `entity_type='capability'` and `action='restore'`-style sentinel actions if needed (extended via the open-vocabulary contract; see §D6).

## D3. Actor + intent context (contextvars)

```python
# audit/context.py
actor_var: ContextVar[CurrentActor | None] = ContextVar("audit.actor", default=None)
intent_var: ContextVar[IntentContext | None] = ContextVar("audit.intent", default=None)


@dataclass(frozen=True, slots=True)
class IntentContext:
    intent_hash: str            # 'idem:...' / 'agent:...' / 'sess:...' / 'req:...'
    intent_metadata: dict[str, Any]
```

Set by middleware (§D4) once per request. Read by `record(...)` and by the mapper listeners.

`asyncio.TaskGroup` and ordinary `await` propagate contextvars correctly. Background tasks (`BackgroundTasks`) inherit the request's contextvars at the moment they're enqueued — that's the right semantic ("the email goes out *because* this request happened").

If an audit write happens *outside* a request (e.g. an arq worker handling a scheduled job), the worker harness sets its own `actor_var` from the job's serialised context. We don't ship arq today; documented in §D9 for when the workers epic lands.

## D4. FastAPI middleware

```python
# audit/middleware.py
class AuditContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        intent_hash, intent_metadata = compute_intent_hash(request)
        actor = await maybe_resolve_actor(request)  # None on /auth/* etc.

        atok = actor_var.set(actor)
        itok = intent_var.set(IntentContext(intent_hash, intent_metadata))
        try:
            return await call_next(request)
        finally:
            actor_var.reset(atok)
            intent_var.reset(itok)
```

Wired in `main.py` after the identity middleware so `current_actor`'s JWT decode runs before `maybe_resolve_actor`. Order:

1. Identity middleware (`current_actor` dependency available).
2. Tenant context dependency (per route — sets `app.current_org` GUC).
3. **Audit context middleware** (this).

For the middleware to know the actor it does its own lightweight JWT decode (best-effort — drops to `None` on missing / expired token). The route-level `current_actor` dependency stays the source of truth for hard auth checks.

## D5. Redaction

Global denylist lives in `audit/redact.py`:

```python
GLOBAL_REDACT: frozenset[str] = frozenset({
    "password_hash",
    "token_hash",          # magic_link_tokens, org_invitations, project_shares
    "api_key_hash",        # api_keys
    "key_hash",            # api_keys (alias)
    "client_secret",
    "raw_token",           # paranoid catch-all
})
```

Two extension points:

1. **Per-model**: `__audit_redact__: frozenset[str]` on an `AuditedModel` subclass merges with the global set.
2. **Per-call**: `record(..., extra_intent_metadata=…)` — caller decides what additional fields to omit / hash if non-trivial.

`redact(diff)` walks `before` / `after` keys; matching keys are replaced with the literal string `"<redacted>"`, never dropped (presence of a key is itself signal).

## D6. `entity_type` open vocabulary contract

`audit_log.entity_type` is `TEXT` with no CHECK constraint by design.

Convention (enforced by the CLAUDE.md guide and code review, not by SQL):

- **lowercase**, **singular**, **noun**: `organisation`, `project`, `member`, `share`, `capability`, `org_invitation`. NOT `Organisations`, `org_member`, `created_project`.
- Reserved core types listed in CLAUDE.md so downstream doesn't shadow them.
- Downstream picks domain-specific names: `scenario`, `analysis`, `property`, `model_run`. No core change required.

Filter queries are uniform across core and downstream:

```sql
SELECT * FROM audit_log
WHERE organisation_id = $1
  AND entity_type = 'scenario'
  AND entity_id = $2
ORDER BY timestamp DESC;
```

## D7. ADR-010 amendment

Append a section "Extension contract for downstream products":

- `entity_type` is open vocabulary; convention enforced via CLAUDE.md.
- Two write paths (explicit `record(...)` and `AuditedModel` mixin) are both core API.
- `actor_var` / `intent_var` contextvars set by `AuditContextMiddleware` are the canonical handoff.
- `__audit_redact__` extends the global denylist, never replaces it.

This puts the contract in front of any architect / Claude session that reads ADRs before touching audit.

## D8. Documentation for Claude

Two markdown files ship in this change because they're load-bearing for downstream extension:

### `CLAUDE.md` at repo root

Sections, in order:
1. **What FastSaaS is** — three foundation layers (identity → tenancy/authz → audit), and "your domain on top".
2. **Architectural rules** that bind every PR (must-not list):
   - No Department in the hierarchy.
   - `capability` is the only authz API; never `SELECT … FROM capabilities` from a route.
   - `migrator_session_scope` only in service layer.
   - `set_config(name, val, true)` not `SET LOCAL name = $1`.
   - `+100` (dev) / `+200` (test) port shift; CI standard.
   - Branch off `main` for every change (no exceptions).
   - GIVEN / WHEN / THEN test docstrings.
3. **Where to look** — ADRs, use cases, OpenSpec changes, scripts.
4. **Recipes** — copy-paste templates for the most common things: add a tenant-scoped table, add a service method, add an audited domain entity, add a route gated by a capability, add a vitest case, add a Playwright e2e step.
5. **Pointer** to module-level CLAUDE.md files for deeper modules (audit, authz, …).

### `backend/src/fastsaas/audit/CLAUDE.md`

Sections:
1. **When to use which style** — the explicit/mixin decision tree.
2. **Adding a new audited entity (downstream)** — copy-paste class definition, expected `entity_type`, redaction declaration.
3. **Adding audit to a non-CRUD service operation** — explicit `record(...)` recipe.
4. **What NOT to do** — bypass `record(...)` with raw SQL (audit gap), reuse a core `entity_type` for a downstream concept (collision), strip `intent_metadata` (loses provenance).
5. **Reading audit_log** — RLS-aware filter examples for compliance officers.

## D9. Test strategy

Unit:
- `intent.compute_intent_hash` for each prefix branch.
- `redact.redact` strips global + per-model fields, preserves keys as `"<redacted>"`.
- `AuditedModel` listener fires on insert / update / soft-delete-flip / hard-delete; `__audit_skip__` opts out; `__audit_redact__` merges with global.

Integration:
- Each core mutation (orgs / projects / members / shares / capability mints / revokes) produces exactly one (or, for fan-out, the documented count of) `audit_log` rows with the right `actor_id`, `entity_type`, `action`, `intent_metadata.org_id`.
- `password_hash` / `token_hash` / `api_key_hash` never appear in `audit_log.diff` even when the underlying ORM model carries them.
- Compliance-officer query path returns rows from another org; vanilla member's same query is RLS-blocked.

E2E (extends the existing smoke):
- After dev-bypass + create org + create project, hit a (future) admin endpoint and assert audit rows exist for `organisation/create` and `project/create`. Initially — direct DB peek through migrator session is enough.

## D10. Worker / background-task semantics (forward-compat)

`BackgroundTasks` inherits the request's contextvars at enqueue time — so `record(...)` from inside `send_org_invitation` etc. still sees the right actor. When arq lands (per ADR-005), the worker harness must set `actor_var` from the serialised job context before invoking the handler; documented here so the future change has a contract to honour.
