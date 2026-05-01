# FASTSAAS

Open-source fullstack SaaS starter-kit (FastAPI + React + Vite + TanStack + shadcn/ui).

> **Status:** specification only. No code yet. See `requirements/vision/vision-and-scope.md` for the v0.2 vision.

## Architecture in one paragraph

A modular SaaS scaffold with strict tenant isolation (Postgres RLS + application-level guards), an Actor-Centric identity model that treats AI agents as first-class citizens (HUMAN / AGENT / SERVICE), a capability-based access model with role bundles for ergonomic admin UX, an immortal audit log with `intent_hash` grouping, and a phased design-system that turns into a per-org brand customisation feature. The frontend is a pure SPA on React + Vite + TanStack + shadcn/ui (no Node.js in production).

## Layout

```
fastsaas/
├── requirements/
│   ├── vision/
│   │   └── vision-and-scope.md                 — Wiegers Vision & Scope (v0.2)
│   ├── decisions/                              — Architectural Decision Records (ADRs)
│   │   └── ADR-005..ADR-012                    — accepted; foundational architecture
│   ├── formal/use-cases/                       — Wiegers/Cockburn use cases
│   │   └── UC-001..UC-010                      — access scenarios driving the design
│   └── reference/                              — research notes informing decisions
│       ├── react-ui-libraries-primer.md        — shadcn ecosystem deep-dive
│       └── access-model-rbac-vs-capability.md  — RBAC vs capability-based analysis
└── openspec/
    └── changes/
        └── platform-saas-core-architecture-spike/    — the foundational spike
            ├── proposal.md
            ├── design.md                       — 15 decisions, all accepted
            └── tasks.md
```

## Status of decisions

All 15 spike decisions are accepted in `openspec/changes/platform-saas-core-architecture-spike/design.md`.

| Round | Decisions | ADRs written | ADRs scheduled |
|------:|----------:|-------------:|---------------:|
| 1 | 10 | 8 (ADR-005..012) | — |
| 2 | 5 | — | 5 (ADR-013..017) + 2 amendments |

Round 2 ADRs cover Authorization (capabilities + role bundles), Hierarchy (Org → Department → Project), SERVICE actor type, Org policy on capabilities, and API keys — plus amendments to ADR-007 (RLS) and ADR-009 (actor model). Scheduled in spike `tasks.md` Phase 2.

## Use cases (8)

Drove Round 2 architectural changes by surfacing real-world access scenarios:

| ID | Scenario |
|----|----------|
| UC-001 | Practitioner shares read-only project with external client |
| UC-002 | Org with isolated departments using different modules |
| UC-003 | Personal AI agent (Claude / Cursor via MCP) acting on behalf of HUMAN |
| UC-004 | AI Command Bar (CMD+K) — HUMAN action via LLM-translated intent |
| UC-005 | Bulk pipeline SERVICE — org-wide automated workflow |
| UC-007 | Org-level SERVICE actor (no HUMAN parent) |
| UC-008 | API key rotation and revocation lifecycle |
| UC-010 | Org policy on AGENT/SERVICE capabilities |

## Reference research

- `requirements/reference/react-ui-libraries-primer.md` — what "shadcn/ui" actually is, beyond a component library (CLI, registry, blocks, charts, ecosystem, AI integration).
- `requirements/reference/access-model-rbac-vs-capability.md` — comparative analysis of RBAC vs capability-based vs hybrid against all UCs and industry analogues (AWS IAM, GCP IAM, GitHub, Linear, Vault, K8s).

## License

TBD — to be set when code arrives.
