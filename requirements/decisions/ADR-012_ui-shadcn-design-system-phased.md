---
tags: [decision, status/accepted, category/frontend, priority/medium]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-004_frontend-stack]]"
 - "[[ADR-007_multi-tenant-isolation]]"
 - "[[ADR-011_frontend-project-layout]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-012: UI — shadcn/ui canonical + phased design-system-as-feature

## Status
Accepted

## Context

ADR-004 locked the frontend foundation (React + Vite + Radix + Tailwind). What remained open is the concrete component library on top, plus how the design system surfaces to end-users (Storybook? Theme picker? Brand customisation?).

The forces:

- We need a productive component baseline by day-one of `platform` bootstrap.
- AI-assisted development (Claude / Cursor as primary tooling) skews strongly toward shadcn-style ecosystems; that's where most reference material lives.
- Pilots and corporate customers (Acme Consulting, Globex) will eventually want brand customisation — colours, radius, font.
- FASTSAAS-vision describes a multi-style picker. FASTSAAS will need the same in time.
- Maintaining a separate Storybook codebase for a tiny custom-component count is overhead with low return.

This ADR locks both the **library** and the **roll-out plan** for the user-facing design-system surface. The roll-out is intentionally phased — the SaaS-core epic ships only what's needed; the full design-system-admin page is a separate epic.

## Decision

### Library: shadcn/ui canonical

- **Components, blocks, and charts** all from the official shadcn registry (https://ui.shadcn.com/).
- Underlying: Radix UI primitives + Tailwind CSS **v4** + Class Variance Authority (per ADR-004).
- Copy-paste model: components live in `frontend/src/components/ui/`; we own the code.
- **No Tremor** — shadcn-charts cover dashboard needs.
- **No Park UI / Catalyst / Mantine / MUI** — would break the Radix foundation or move us into npm-package model.

### Initial component pull (bootstrap, #2 in platform)

```bash
npx shadcn@latest add \
 button input label form select textarea checkbox radio-group switch \
 dialog sheet alert-dialog popover dropdown-menu tooltip toast \
 card badge avatar separator skeleton tabs accordion \
 table calendar
```

Plus blocks: `login-04` (or chosen variant) and `sidebar-07` (or chosen variant).

### Phased design-system-as-feature

| Phase | What ships | Where |
|-------|-----------|-------|
| **1** — in epic #16 | `organisations.theme JSONB` (per ADR-007) + 3–5 pre-defined themes (Default, Modern, Corporate, Dark, High-contrast) + simple `<ThemePicker>` in Settings | Bootstrap and beyond, this epic |
| **2** — new "Brand Customisation" epic | `/admin/design-system` admin page — embedded component catalogue + visual theme editor (color sliders, radius, font) + live preview + save-as-org-brand | Separate epic, post-#16 |
| **3** — optional, dev-only | Storybook on `localhost:6006` for component development | When ≥ 20 custom (non-shadcn) components exist; not required for SaaS-core |
| **4** — far future, FASTSAAS | Public Storybook on `design.fastsaas.dev` + Chromatic visual regression | When/if FASTSAAS becomes a public design-system product |

### Storybook in v1 SaaS-core: NOT used

- shadcn's canonical catalogue at https://ui.shadcn.com replaces the need for an internal one.
- Solo developer + Claude Code do not need a handoff tool.
- Bundle / setup / maintenance cost is not justified yet.

### Custom FASTSAAS registry (future)

When FASTSAAS-specific components emerge (`PropertyCard`, `ScenarioComparison`, `LeaseEditor`, …), publish them as a shadcn-compatible registry at e.g. `design.fastsaas.com/registry/...`. Pilots and projects can then `npx shadcn add <url>`. This is a Phase 2/3 concern, not v1.

## Alternatives Considered

### Tremor as primary library

- Strong dashboard / chart story.
- **Rejected:** specialised; not a general-purpose UI set. shadcn-charts now cover the dashboard need. Tremor remains a possible *complement* if future requirements outgrow shadcn-charts; no commitment now.

### Park UI

- Multi-framework (React + Vue + Solid) from one source.
- **Rejected:** built on Ark UI, not Radix UI — would force an ADR-004 reversal.

### Catalyst (Tailwind UI commercial)

- Highest design polish; from the Tailwind team.
- **Rejected:** $299 paid; redistribution restrictions; would block any public-ready future.

### Embedded Storybook in admin (iframe)

- Reuse the full Storybook feature set behind auth.
- **Rejected:** iframe cross-frame messaging is fragile; bundle bloats by 5–10 MB; UX rooted in dev tools doesn't fit a product surface.

### Storybook in v1 (canonical use)

- Industry-standard component catalogue + visual regression tooling.
- **Deferred:** we don't yet have a meaningful number of custom components. Reconsider in Phase 3 when ≥ 20 exist.

## Consequences

### Positive

- shadcn's ecosystem is the largest in React UI today; AI-coding alignment is excellent.
- Copy-paste model keeps every component fully under our control — no npm upgrade pain, no abstraction wall.
- Phased roll-out lets epic #16 ship without building a full admin design page, while still laying the **right foundation** (`organisations.theme`, CSS variables, simple picker). Phase 2 becomes additive, not a refactor.
- Custom-built `/admin/design-system` (Phase 2) is strategically more valuable than embedded Storybook because it integrates auth, RBAC, multi-tenancy, and per-org theme persistence natively — turning the design system into a product feature, not a developer tool.
- shadcn-charts inclusion eliminates the previously-planned Tremor dependency.

### Negative

- We maintain the shadcn registry of components in our repo by hand; canonical updates require manual diff review. Acceptable trade for full code ownership.
- Tailwind v4 is newer than v3; small risk of edge-case shadcn incompatibility. Mitigated by sticking to canonical components and watching shadcn release notes.
- The Phase 2 admin page must catalogue components manually (no automatic story discovery); each new component needs a registry entry. Acceptable at the modest count we expect.

## Open Questions

- Specific shadcn fork/version pin for Tailwind v4 — verify at install time; canonical now supports v4.
- Pre-defined theme palettes for Phase 1 picker — copy 3–5 from `https://ui.shadcn.com/themes` initially.
- Phase 2 epic title and acceptance criteria — captured as a separate backlog issue alongside this ADR.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #10]]
- [[ADR-004_frontend-stack]]
- [[ADR-007_multi-tenant-isolation]]
- [[ADR-011_frontend-project-layout]]
- [[../reference/react-ui-libraries-primer|requirements/reference/react-ui-libraries-primer.md]] — extended primer
- shadcn/ui — https://ui.shadcn.com/
- shadcn philosophy / Open Code — https://ui.shadcn.com/docs
- shadcn registry schema — https://ui.shadcn.com/docs/registry
