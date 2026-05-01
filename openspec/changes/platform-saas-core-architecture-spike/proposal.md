---
title: Platform SaaS core — overall architecture design (spike)
status: in_progress
linked_issue: the SaaS-core architecture spike
hub_parent: the SaaS-core epic
created: 2026-05-01
---

## Why

Epic [the SaaS-core epic](https://github.com/FASTSAAS/fastsaas/issues/16) (*Platform SaaS core*) is decomposed into 7 implementation issues in `platform` (`#2` bootstrap → `#8` E2E). Each of them depends on cross-cutting decisions that cannot be made independently without producing inconsistent code: how isolation works, how the actor model relates to users, how an `intent_hash` is computed, how the frontend project is laid out, etc.

Without locking these decisions first, sub-issues will either block on each other or pick locally reasonable but mutually inconsistent approaches.

## What Changes

This spike does not change behavior. It produces design artefacts:

- **NEW** ADR-005..ADR-0NN in `fastsaas/requirements/decisions/` for each non-trivial decision.
- **NEW** Consolidated `design.md` in this change directory referencing all ADRs and showing how the platform is laid out.
- **UPDATE** `platform/CLAUDE.md` with locked stack details where relevant.
- **UPDATE** `fastsaas/requirements/open-questions/*.md` — close or update questions covered by ADRs.

After this spike is archived, each sub-issue under #16 picks up with a concrete ADR/section reference for its approach.

## Decisions in scope (10)

1. Async strategy — sync vs async FastAPI; long-running task runner.
2. Hierarchy primary keys — UUID v7 vs serial; cascade rules.
3. Multi-tenant isolation — Postgres RLS vs application-level filter.
4. Auth flow — JWT short-lived + refresh; cookies vs header; magic-link TTL; OAuth providers.
5. Actor vs User — one table or two.
6. `intent_hash` algorithm — canonical payload-to-hash format.
7. Audit log shape — table with JSONB diff vs event sourcing; retention.
8. OpenAPI codegen tool — `openapi-typescript` / `orval` / hand-rolled.
9. Frontend project layout — feature- vs layer-folders; UI-state library choice.
10. Component library variant — concrete shadcn-style set.

See `design.md` for current state of each decision.

## Out of scope

- Implementation of any of the above (handled in sub-issues #2–#8 in platform).
- FASTSAAS-specific runtime concerns (Model Registry, Execution Engine, FASTSAAS 5-level hierarchy) — covered by epic [#2](https://github.com/FASTSAAS/fastsaas/issues/2).
