---
tags: [decision, status/accepted, category/data-model, priority/high]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-006_primary-keys-and-cascade]]"
 - "[[ADR-008_auth-flow]]"
 - "[[ADR-010_audit-log-shape]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-009: Actor model — Class Table Inheritance with users/agents children

## Status
Accepted

## Context

The FASTSAAS-CORE vision (FE-CORE-1) calls for an Actor-Centric identity model where both humans and AI agents are first-class actors in the system. AGENT actors carry a `parent_actor_id` pointing at the HUMAN on whose behalf they act, supporting accountability and audit.

In schema terms, HUMAN and AGENT actors have substantially different attribute sets:

- **HUMAN:** email, password hash, OAuth identities, locale, timezone, profile.
- **AGENT:** API key hash, allowed scopes, creator (Claude / Cursor / MCP / manual), last-used timestamp.

Three patterns can express this in SQL. The choice affects FK integrity for `audit_log` (per ADR-010), nullable-bloat in shared columns, query ergonomics, and the cost of adding future actor types (e.g. a `MODEL` actor for FASTSAAS epic #2 model containers, or a `SERVICE` for machine-to-machine).

## Decision

**Class Table Inheritance (CTI) — `actors` parent table + `users` and `agents` 1:1 child tables.** All foreign keys in audit / membership / ownership point at `actors.id`, regardless of subtype.

### Schema

```sql
CREATE TABLE actors (
 id UUID PRIMARY KEY, -- UUID v7 per ADR-006
 actor_type TEXT NOT NULL, -- 'HUMAN' | 'AGENT'
 parent_actor_id UUID NULL REFERENCES actors(id), -- AGENT.parent → HUMAN
 display_name TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 deleted_at TIMESTAMPTZ NULL, -- soft-delete per ADR-006
 CONSTRAINT actor_type_valid CHECK (actor_type IN ('HUMAN', 'AGENT')),
 CONSTRAINT agent_has_parent CHECK (actor_type <> 'AGENT' OR parent_actor_id IS NOT NULL),
 CONSTRAINT human_no_parent CHECK (actor_type <> 'HUMAN' OR parent_actor_id IS NULL)
);

CREATE TABLE users (
 actor_id UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
 email CITEXT UNIQUE NOT NULL,
 password_hash TEXT NULL, -- NULL for OAuth-only users
 email_verified BOOLEAN NOT NULL DEFAULT FALSE,
 locale TEXT NOT NULL DEFAULT 'en',
 timezone TEXT NOT NULL DEFAULT 'UTC',
 created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE oauth_identities (
 user_actor_id UUID NOT NULL REFERENCES users(actor_id) ON DELETE CASCADE,
 provider TEXT NOT NULL, -- 'google' | 'microsoft'
 provider_uid TEXT NOT NULL,
 PRIMARY KEY (provider, provider_uid)
);

CREATE TABLE agents (
 actor_id UUID PRIMARY KEY REFERENCES actors(id) ON DELETE CASCADE,
 api_key_hash TEXT NOT NULL,
 allowed_scopes TEXT[] NOT NULL DEFAULT '{}',
 created_via TEXT NOT NULL, -- 'claude' | 'cursor' | 'mcp' | 'manual'
 last_used_at TIMESTAMPTZ NULL
);
```

### v1 SaaS-core scope

- The schema for `actors`, `users`, `agents`, `oauth_identities` ships in bootstrap (#2 in platform).
- **AGENT-actor creation/management endpoints are NOT in v1.** Only HUMAN registration is wired up. AGENT lifecycle ships with the future MCP epic.

## Alternatives Considered

### Single-Table Inheritance (STI) — one `actors` table with nullable HUMAN-only / AGENT-only columns

- One JOIN-free lookup; trivial Pydantic model.
- **Rejected:** every HUMAN-only column (email, password_hash, oauth) becomes nullable; CHECK constraints to enforce "if HUMAN then email NOT NULL" become baroque. Adding new actor types pollutes the shared table further.

### Fully separate tables (`users` and `agents`, no parent table)

- Cleanest per-table schemas.
- **Rejected:** breaks polymorphic FKs in `audit_log`. Without a parent table, audit must use a polymorphic pseudo-FK (`actor_type` + `actor_id`) without referential integrity — and we cannot guarantee the row exists.

## Consequences

### Positive

- **FK integrity for `audit_log.actor_id`** is preserved; every audit row references a real actor regardless of type. Compliance leverage.
- **Clean child schemas** — `users.email NOT NULL`, `agents.api_key_hash NOT NULL`; no nullable bloat.
- **Extensibility** — adding a future actor type (e.g. `MODEL` for FASTSAAS epic #2 or `SERVICE` for M2M) is just a new child table + extending the `CHECK` constraint.
- **CASCADE** from `actors` to `users`/`agents` keeps the 1:1 invariant: deleting `actors` removes the child automatically.

### Negative

- Two INSERTs to create a user (`actors` + `users`) — wrapped in a transaction; trivial cost.
- Common queries that need user fields require a JOIN. For listing humans we instead query `users` directly + JOIN to `actors` only when type-agnostic data (display_name) is needed.
- Pydantic / SQLModel needs a `UserResponse` view that joins both — handled in the API layer.

## Open Questions

- AGENT cascade behaviour when parent HUMAN is soft-deleted: cascade soft-delete the AGENT, or keep it usable? Defer to MCP epic.
- API-key rotation policy for agents. Defer to MCP epic.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #5]]
- [[ADR-006_primary-keys-and-cascade]]
- [[ADR-008_auth-flow]]
- [[ADR-010_audit-log-shape]]
