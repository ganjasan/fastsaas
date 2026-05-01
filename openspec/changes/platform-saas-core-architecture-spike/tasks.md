---
title: Platform SaaS core — spike tasks
linked_issue: the SaaS-core architecture spike
---

# Tasks

## Phase 1 — Decide ✅ DONE (Round 1) ✅ DONE (Round 2)

### Round 1 — initial 10 decisions (2026-05-01)

- [x] **Decision 1: Async strategy** → **B** async FastAPI + arq workers. Output: ADR-005.
- [x] **Decision 2: Hierarchy primary keys** → **UUID v7** + soft-delete domain + immortal audit_log. Output: ADR-006.
- [x] **Decision 3: Multi-tenant isolation** → **C** RLS + app-level WHERE (defense-in-depth) + `organisations.theme` JSONB. Output: ADR-007.
- [x] **Decision 4: Auth flow** → JWT 15min access + 30d rotating refresh + httpOnly cookies (hybrid storage) + Google + M365. Output: ADR-008.
- [x] **Decision 5: Actor vs User** → **CTI** — `actors` parent + `users`/`agents` children. Output: ADR-009.
- [x] **Decision 6: `intent_hash`** → **D** Hybrid with prefixed source (`idem:` / `agent:` / `sess:` / `req:`); idempotency cache deferred. Output: design.md section.
- [x] **Decision 7: Audit log shape** → **A** classic `audit_log` + `{before, after}` JSONB diff. Output: ADR-010.
- [x] **Decision 8: OpenAPI codegen** → **orval** + react-query + MSW mocks. Output: design.md section.
- [x] **Decision 9: Frontend layout** → hybrid features+ui+lib + Zustand + co-located tests. Output: ADR-011.
- [x] **Decision 10: Component library** → shadcn/ui canonical + Tailwind v4 + phased design-system-as-feature; Storybook deferred. Output: ADR-012 + new backlog item for Phase 2 brand-customisation epic.

### Round 2 — access-model gap (2026-05-01)

After Round 1, surfaced UC-001..UC-010 (8 use cases) that exposed gaps:

- [x] **Decision 11: Authorization model** → **Hybrid — capabilities as primitive + role bundles as presentation**. Output: ADR-013 (post-merge).
- [x] **Decision 12: Hierarchy extension** → **Org → Department → Project (3-level)**. Output: ADR-014 (post-merge).
- [x] **Decision 13: Actor types** → **add SERVICE** (HUMAN + AGENT + SERVICE). Output: ADR-015 (post-merge).
- [x] **Decision 14: Org policy mechanism** → **declarative rules limiting AGENT/SERVICE capabilities**, with audit + override. Output: ADR-016 (post-merge).
- [x] **Decision 15: API Keys** → **separate `api_keys` table; multiple keys per actor; per-key scope restriction; soft-revoke; rotation grace period**. Output: ADR-017 (post-merge) + further amendment to ADR-009 (remove `api_key_hash` from `agents`/`services`).

### Use Cases formalized (Round 2 driver)

- [x] UC-001 — Practitioner shares read-only with client.
- [x] UC-002 — Org with departments — isolated modeling.
- [x] UC-003 — Personal AI agent via MCP.
- [x] UC-004 — AI Command Bar (CMD+K).
- [x] UC-005 — Bulk pipeline service.
- [x] UC-007 — Org-level service account (no HUMAN parent).
- [x] UC-008 — API key rotation and revocation.
- [x] UC-010 — Org policy on AGENT capabilities.

### Reference research (Round 2)

- [x] `requirements/reference/access-model-rbac-vs-capability.md` — full comparative analysis driving Decision 11.

## Phase 2 — Document

### Round 1 ADRs (created)
- [x] ADR-005..ADR-012 written (8 ADRs).
- [x] `platform/CLAUDE.md` aligned with Round 1 stack (PR #1 merged).

### Round 2 ADRs (to write)
- [ ] ADR-013 — Authorization model (capabilities + role bundles).
- [ ] ADR-014 — Hierarchy: Org → Department → Project (3-level).
- [ ] ADR-015 — Actor types: SERVICE addition.
- [ ] ADR-016 — Org policy mechanism.
- [ ] ADR-017 — API Keys (separate table, multi-key per actor, per-key scope, lifecycle).
- [ ] **Amend** ADR-007 — add `app.current_department` RLS context + compliance role audit access.
- [ ] **Amend** ADR-009 — (1) add `actor_type=SERVICE`; `services` child table; CHECK constraint update; (2) **remove `api_key_hash` from `agents` and `services`** — superseded by `api_keys` table per ADR-017.

### Open-questions cleanup
- [ ] Update / close affected files in `fastsaas/requirements/open-questions/` (`Resource Limits.md` and any others touched).
- [ ] Backfill `traces_to:` frontmatter in this change → epic #16, ADR-004, ADR-002.

## Phase 3 — Verify

### Round 1
- [x] All 10 Round 1 decisions show 🟩 in `design.md`.
- [x] Each sub-issue under #16 (platform #2..#8) has a comment linking to the ADR or design section that informs its approach.

### Round 2
- [x] Decisions 11–15 show 🟩 in `design.md`.
- [ ] Sub-issues #2..#8 acceptance criteria updated to reflect Round 2 (capabilities, departments, SERVICE actor, policies, API keys).
 - [ ] #2 Bootstrap — schema includes `capabilities`, `departments`, `department_members`, `services`, `org_policies`, **`api_keys`**.
 - [ ] #3 Identity — capability provisioning at register / accept-invite; **API key creation/management endpoints + UI**.
 - [ ] #4 Tenants — rename to "Multi-tenant hierarchy + access model"; add departments + capabilities + per-project guest membership.
 - [ ] #5 Audit — `intent_metadata.capability_id` and **`intent_metadata.api_key_id`** reference.
 - [ ] #6 UI — admin pages show roles (presentational); **API keys list + revoke UI**; capability detail Phase 2.
 - [ ] #7 Observability — capability check failures + **API key reuse-after-revocation** monitored.
 - [ ] #8 E2E — verify per-project guest, AGENT scope, department isolation, **API key flow (create + use + revoke)**.

### Common
- [ ] Spike issue #17 acceptance criteria all checked.
- [ ] `/dd:openspec-verify` passes against this change.

## Phase 4 — Ship

- [ ] PR opened from `spike/17-platform-saas-core-architecture` → `main`.
- [ ] Archive change after PR approval (per Drydock convention: archive in same PR as merge).
- [ ] Sync delta specs to `openspec/specs/` — likely none for a spike (no behavioral change).
- [ ] Close issue #17.
