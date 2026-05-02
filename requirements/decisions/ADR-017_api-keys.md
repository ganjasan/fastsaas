---
tags: [decision, status/accepted, category/security, priority/high]
created: 2026-05-01
decided: 2026-05-01
amends: ["ADR-009_actor-model-cti"]
traces_to:
  related:
    - "[[ADR-008_auth-flow]]"
    - "[[ADR-009_actor-model-cti]]"
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
    - "[[ADR-016_org-policy-mechanism]]"
  use_cases:
    - "UC-003 (personal AGENT via MCP)"
    - "UC-005 (bulk pipeline service)"
    - "UC-007 (org-level service account)"
    - "UC-008 (API key rotation and revocation)"
  spike: platform-saas-core-architecture-spike
  epic: ganjasan/fastsaas (Identity & Access epic; issue TBD)
---

# ADR-017: API Keys — separate table, multi-key per actor, per-key scope

## Status
Accepted

## Context

ADR-008 covered HUMAN session auth (JWT via httpOnly cookie). ADR-009 (Round 1) embedded an `api_key_hash` column inside `agents` and `services` for programmatic access — implying one key per actor. Round 2 use cases revealed this is too restrictive:

- **UC-003 [A4]:** a HUMAN may hold several AGENT API keys for the same agent identity (laptop Claude + desktop Cursor + CI integration); rotation requires both old and new keys to be valid concurrently for a grace period.
- **UC-005 [A5]:** SERVICE keys must rotate on a regular cadence; old + new must coexist during the grace window.
- **UC-008** (this round's UC): full API-key lifecycle requires per-key audit, per-key scope, and granular revocation.

Additionally, HUMAN actors themselves want personal API keys (Jupyter notebook scripts, ad-hoc CLI). Round 1 had no story for this.

## Decision

**Move API keys to a dedicated `api_keys` table with multiple keys per actor, optional per-key scope restriction, soft revocation, and rotation grace period. The `api_key_hash` columns on `agents` and `services` are removed (amends ADR-009).**

### Token format

```
apz_<actor_type>_<43-char-base62>

Examples:
  apz_human_8f3cVKtLm9pQRwzN2xYbHsT3uE6FjZ4dWqX1bYn7aP5v
  apz_agent_a91krNxB3vYsTuPpJgQ4MdH7eKzL2cXiVqR5fW8nE6mZ
  apz_service_zz72YpQwL3bKcVnXmJ4fH9rG6tDsNvU5aE1iZ8oW7xT
```

- 32 random bytes → base62 encoded (~43 chars).
- Prefix carries actor type — debugging, secret-scanner registration, log filtering.
- Total length ≈ 55 characters; 256-bit entropy.

### Schema

```sql
CREATE TABLE api_keys (
  id                    UUID PRIMARY KEY,                       -- UUID v7
  actor_id              UUID NOT NULL REFERENCES actors(id),
  key_hash              TEXT NOT NULL,                          -- sha256(token), salted with deployment-secret
  key_prefix            TEXT NOT NULL,                          -- 'apz_agent_8f3c' for display
  name                  TEXT NOT NULL,                          -- 'My laptop Claude' / 'Nightly Pipeline'
  scope_restriction     JSONB DEFAULT NULL,                     -- optional capability subset; NULL = inherit all of actor's capabilities

  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_by            UUID NOT NULL REFERENCES actors(id),
  last_used_at          TIMESTAMPTZ NULL,
  last_used_ip          INET NULL,

  expires_at            TIMESTAMPTZ NULL,                       -- optional TTL
  revoked_at            TIMESTAMPTZ NULL,
  revoked_by            UUID REFERENCES actors(id),
  revoked_reason        TEXT NULL,                              -- 'rotated' | 'compromised' | 'unused' | 'manual'
  rotation_grace_until  TIMESTAMPTZ NULL,                       -- both old + new valid until this

  metadata              JSONB DEFAULT '{}'                      -- {client_hint, ip_allowlist, rate_limit, ...}
);

CREATE UNIQUE INDEX idx_keys_hash ON api_keys (key_hash) WHERE revoked_at IS NULL;
CREATE INDEX idx_keys_actor       ON api_keys (actor_id) WHERE revoked_at IS NULL;
CREATE INDEX idx_keys_prefix      ON api_keys (key_prefix);
```

### Removed from ADR-009

```sql
-- Removed (amendment to ADR-009)
ALTER TABLE agents   DROP COLUMN api_key_hash;
ALTER TABLE services DROP COLUMN api_key_hash;
```

### Authentication flow

1. Client sends `Authorization: Bearer apz_<type>_<random>`.
2. Auth middleware: regex format check → fast 401 on malformed.
3. Compute `sha256(token)` (with deployment salt) → look up in Redis (5-minute cache); fall through to DB if miss.
4. Validate: `revoked_at IS NULL`, `expires_at IS NULL OR expires_at > NOW()`, owning actor not soft-deleted.
5. Set request context: `actor_id`, `api_key_id`, `key_scope` (if `scope_restriction` present).
6. Set RLS context (per ADR-007): `app.current_org`.
7. Capability check (per ADR-013): effective capabilities = `actor.capabilities ∩ key.scope_restriction` (when restriction present).
8. Async update `last_used_at`, `last_used_ip` (fire-and-forget; cap once per minute per key to limit write amplification).
9. Audit row carries `intent_metadata.api_key_id`.

### Per-key scope restriction

A key may carry a strict subset of its actor's capabilities. Use cases:

- HUMAN creates a read-only personal key for a Jupyter notebook (own role permits write, but key cannot).
- AGENT key restricted to a specific project subset (per UC-003 [A2], UC-008 [A2]).
- SERVICE key with `metadata.rate_limit = {model_executions_per_hour: 100}`.

Effective capabilities are always the intersection — a key cannot escalate beyond its actor's grants.

### Lifecycle

| Phase | Behaviour |
|-------|-----------|
| **Create** | Generate token; store `sha256(salt + token)`; show full token ONCE. |
| **Use** | Auth middleware loads, checks; updates `last_used_*` async. |
| **Rotate** | Mint new key; old key gets `rotation_grace_until = NOW + 7 days` (org-policy configurable); both valid during grace; cron auto-revokes old after grace. |
| **Revoke (manual)** | Soft-revoke (`revoked_at` set); Redis cache invalidated immediately; subsequent requests with token → 401. |
| **Revoke (cascade)** | When actor soft-deleted → all their keys revoked. |
| **Expire** | Cron sets `revoked_at` once `expires_at` passes; behaves identically to manual revocation. |

Revoked keys are **never deleted physically** — `key_hash` retained to detect reuse-after-revocation (high-priority audit + Slack alert).

### Org policy interactions (per ADR-016)

Org policies can constrain key creation:

- Maximum keys per actor.
- Default expiry required (`expires_at` cannot be NULL).
- IP allowlist required for SERVICE keys.
- Forced rotation interval (auto-revoke at age N days).

### Audit (per ADR-010)

Every action via API key writes audit with `intent_metadata.api_key_id`. Reports built on this:

- "Show all actions performed by key X."
- "Detect any use of revoked keys" — replay-after-revoke triggers high-priority alert.
- "Keys created > 90 days ago, used from new IP" — anomaly detection.

## Alternatives Considered

### Single key per actor (ADR-009 Round 1)

Implies destructive rotation (one moment of downtime), no parallel use across devices. Rejected.

### Asymmetric keys (public / private)

Heavyweight; key distribution problem doesn't go away. Rejected for v1.

### JWT-as-API-key (long-lived JWTs)

Loses immediate revocation (JWT is stateless); blacklist required anyway. Rejected — the `api_keys` table is just a cleaner blacklist source.

### Per-resource API keys (Stripe-style restricted keys)

`scope_restriction` JSONB covers this — not a separate mechanism.

## Consequences

### Positive

- Multiple keys per actor → realistic device + integration topology.
- Per-key scope restriction → defense-in-depth (compromised key has narrower blast radius than compromised actor).
- Per-key audit → key X's full action history queryable from audit_log.
- Soft-revoke + retained hash → forensic value preserved; reuse-detection works.
- Prefix-based token format → ready for GitHub Secret Scanning partner enrollment post-public-launch.

### Negative

- Salting sha256 with a deployment secret means: lose the secret, lose all existing key validations. Documented in ops runbook; backed up alongside DB encryption keys.
- `api_keys` table grows monotonically (soft-delete only). Acceptable; periodic archive after N years possible.
- HUMAN session auth (cookie/JWT) and HUMAN programmatic auth (API key) are two flows — both must be supported in middleware.

## Open Questions

- Salt algorithm: HMAC-SHA-256 with deployment secret vs sha256(secret + token). HMAC is technically stronger; finalise in bootstrap.
- Stripe-style `_test_` / `_live_` prefix for env separation: Phase 2 (no schema impact).
- GitHub Secret Scanning partner program enrollment: post-public-launch.
- Webhook on key events (created / revoked / used-after-revoke): Phase 2.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #15]]
- [[../formal/use-cases/UC-003_personal-ai-agent-via-mcp]]
- [[../formal/use-cases/UC-005_bulk-pipeline-service]]
- [[../formal/use-cases/UC-007_org-level-service-account]]
- [[../formal/use-cases/UC-008_api-key-rotation-and-revocation]]
- [[ADR-008_auth-flow]] — JWT/session companion
- [[ADR-009_actor-model-cti]] — amended (api_key_hash removed)
- [[ADR-013_authorization-capabilities-role-bundles]] — capability model api_keys depend on
- [[ADR-016_org-policy-mechanism]] — policies on key creation
- GitHub Secret Scanning partners — https://docs.github.com/en/code-security/secret-scanning/secret-scanning-partner-program
