---
tags: [decision, status/accepted, category/frontend, priority/medium]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-004_frontend-stack]]"
 - "[[ADR-012_ui-shadcn-design-system-phased]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-011: Frontend project layout & state assignment

## Status
Accepted

## Context

The frontend stack is locked (ADR-004: React + Vite + TanStack Router/Query + Radix + Tailwind). What remains undefined is **how the source tree is organised** and **where each kind of state lives**. These conventions, while modest in code, materially shape onboarding speed, refactor cost, and AI-coding consistency. They should be locked once and respected, not re-litigated per feature.

Two axes:

1. **Folder structure** — feature-folders (vertical), layer-folders (horizontal), or hybrid.
2. **State separation** — what goes in TanStack Query vs Router vs forms vs a UI-state library.

## Decision

### Folder structure: hybrid — `features/<domain>/` + `components/{ui,shared}/` + `lib/` + `stores/`

```
frontend/src/
├── features/ # vertical, domain-aligned slices
│ ├── auth/
│ │ ├── components/ # LoginForm, OAuthButtons, MagicLinkSent
│ │ ├── hooks/ # useCurrentUser, useLogin, useLogout
│ │ ├── routes/ # login.tsx, verify-email.tsx, accept-invite.tsx
│ │ ├── stores/ # only if a feature-local store is justified (rare)
│ │ └── types.ts
│ ├── orgs/
│ ├── projects/
│ ├── settings/
│ └── audit/
├── components/
│ ├── ui/ # shadcn-style copy-paste primitives (per ADR-012)
│ └── shared/ # cross-feature shared (EmptyState, ErrorBoundary, EntityHeader)
├── lib/
│ ├── api/ # custom mutator + orval-generated/
│ ├── auth/ # in-memory tokenStore, JWT decode (per ADR-008)
│ ├── theme/ # theme.ts, applyTheme.ts
│ └── utils/ # cn(), formatters, date helpers
├── stores/ # global Zustand: uiStore (theme, sidebar), toastStore
├── routes/ # TanStack Router root + layouts + error boundaries
├── styles/ # Tailwind imports, theme.css
└── main.tsx
```

### UI state library: Zustand (minimal), used only for genuine UI ephemera

Strict state-assignment rules — to be enforced in code review:

| Kind of state | Where it lives |
|---------------|----------------|
| **Server data** (projects, users, audit entries) | TanStack Query — never elsewhere |
| **URL-derivable state** (current org, filters, page, tab) | TanStack Router params + search params |
| **Form state** (in-progress edits) | React Hook Form + Zod schemas |
| **UI ephemera** (theme, sidebar collapse, toast queue, modal/drawer stack) | Zustand stores in `src/stores/` |
| **Component-local one-shot state** | `useState` |

### Co-located tests

- `LoginForm.tsx` + `LoginForm.test.tsx` in `features/auth/components/`.
- E2E (Playwright) lives in `frontend/e2e/` — separate from per-component tests.
- All test names use the GIVEN/WHEN/THEN pattern (already in `platform/CLAUDE.md`).

## Alternatives Considered

### Pure feature-folders

- Strongest co-location.
- **Rejected:** forces every shared primitive (EmptyState, EntityHeader) into a feature folder it doesn't conceptually belong to.

### Pure layer-folders (`components/`, `hooks/`, `pages/`, `api/`)

- Familiar from MVC / Django.
- **Rejected:** scatters "auth" across five directories. Slow to onboard and to delete.

### Redux Toolkit for UI state

- Industry incumbent for shared state.
- **Rejected:** the actual cross-component UI state in this app is tiny (≤ 10 atoms: theme, sidebar, toasts, modal stack). Redux's machinery would dominate the surface.

### Jotai (atomic state)

- Excellent for many small independent atoms.
- **Rejected:** overkill for the modest state surface; adds a paradigm to learn for marginal benefit.

### Context API only

- Zero dependency.
- **Rejected:** multi-provider trees and re-render storms; insufficient for theme + sidebar + toasts.

## Consequences

### Positive

- Domain code is co-located in `features/`; truly shared UI primitives live in `components/ui/`; cross-cutting infrastructure in `lib/`. A new contributor can find anything within two clicks.
- The state-assignment matrix gives every PR an unambiguous answer to "where does this state belong?", eliminating drift.
- Zustand's footprint (~1.5 KB) is negligible.
- Co-located tests keep authoring and updating tests close to the code they cover.

### Negative

- The `features/X/components/` vs `components/shared/` boundary is a judgement call; reviewers must enforce consistency.
- Strict prohibition on mixing server state into Zustand requires discipline; mitigated by the shared rules table and by review.

## Open Questions

- Stories for `components/ui/` — Storybook vs Ladle vs none. Decided in ADR-012: deferred for v1.
- Naming: `features/auth/` vs `auth/` (no prefix) — locked: keep the `features/` prefix; explicit beats implicit.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #9]]
- [[ADR-004_frontend-stack]]
- [[ADR-012_ui-shadcn-design-system-phased]]
- Zustand — https://github.com/pmndrs/zustand
- Bulletproof React (similar conventions) — https://github.com/alan2207/bulletproof-react
