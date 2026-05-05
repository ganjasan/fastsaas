## Context

The AppShell from #18 was the first cut: get a working chrome on top of shadcn primitives so feature pages have somewhere to live. The operator's reference designs (Render, Extruct admin) show a more curated layout — workspace switcher in the sidebar header, section labels for nav groups, breadcrumb-style topbar, Overview pages composed of cards. FastSaaS-built SaaS surfaces are intended to share that aesthetic, so the chrome is being upgraded once and reused everywhere.

## Goals

- Single `<Shell>` primitive that AppShell, AdminShell (#19), and any future shell flavours all consume — the chrome lives in one place.
- Workspace identity surfaces in the sidebar header (where the user expects it on Render-style products), not the topbar.
- Section labels (UPPERCASE muted) supported for nav groups; org-level dashboard ships without labels (only Projects + Settings today), AdminShell ships with `OPERATIONS` / `CONFIGURATION` per #19.
- Bottom-chrome surface (Status / Changelog / Help / Collapse) so operator-side controls don't bloat the topbar.
- `/orgs/{slug}` becomes an Overview that shows the user's actual data (projects) plus an obvious primary CTA (`+ Create new project`).

## Non-goals

- Functional `⌘K` command palette. Trigger is a placeholder no-op; the real palette is its own epic.
- Real status / health check. Static green pill until #20's Health page lands.
- Notification + changelog feeds. Links to `#` for v1.
- AdminShell implementation — that's #19. This PR ships only the primitive.
- DataTable + form primitives — second half of #5.

## Decisions

### D1 — One `<Shell>` primitive, two thin wrappers (AppShell, AdminShell)

The chrome contract is uniform: sidebar with header + nav sections + bottom chrome, topbar with left + right slots, main outlet. The differences between AppShell and the future AdminShell are in the *content* of those slots (workspace switcher vs "PLATFORM ADMIN" label; org-level nav vs admin nav; user menu vs staff user menu), not the *layout*.

`<Shell>` takes named-slot props (`sidebarHeader`, `sidebarSections`, `sidebarBottom`, `topbarLeft`, `topbarRight`). `<AppShell>` and `<AdminShell>` are 30-line wrappers that build the slot content from feature-specific data.

**Rationale.** Layout drift between two shells is the most likely visual-regression source. Forcing both through one primitive eliminates it at compile time.

### D2 — Workspace switcher moves to sidebar header

Render places the workspace switcher in the sidebar's top-left corner; the topbar carries breadcrumbs + global controls (search, +new, user). The current AppShell mounts the OrgSwitcher in the Topbar, which is a shadcn-default pattern but not the operator's target aesthetic.

The `<WorkspaceSwitcher>` is a renamed + restyled OrgSwitcher rendered as a compact card: avatar tile (initial) + name + chevron, opens the same dropdown with org list + "Create new organisation".

**Rationale.** Match the operator's target. Frees the topbar for breadcrumbs + global actions.

### D3 — Topbar gets a breadcrumb (current section name) on the left

The topbar previously hosted only OrgSwitcher + theme toggle + user menu. After D2, the left side is empty. Filling it with the current section name (`Overview` / `Projects` / `Settings`) gives the user a "where am I" anchor and matches the Render aesthetic.

For v1 the breadcrumb is single-segment (the section). When deeper nav lands (e.g. project detail), it can grow to `Projects / <project-name>`. The breadcrumb is computed from the URL via TanStack Router's matched route in the AppShell (single source of truth).

**Rationale.** Wayfinding + visual symmetry with the right-side controls.

### D4 — Right side of topbar = Search trigger + `+ New` dropdown + user menu

Three controls, in this order, right-aligned. Search trigger is a button with the `⌘K` hint (placeholder no-op for now). `+ New` is a dropdown with "Create project" (uses the active org slug) and "Create organisation" entries — both link to the existing routes (`/orgs/{slug}/projects` with the create dialog open, or `/orgs/new`). User menu carries the email + Logout.

ThemeModeToggle from #18 stays — fits between Search and `+ New` or between `+ New` and user menu, depending on how cluttered the topbar feels at narrow widths.

**Rationale.** All global, non-section-specific actions live on one bar; sidebar focuses on navigation.

### D5 — Sidebar bottom-chrome with Status pill, Changelog, Help, Collapse

Placeholder content for v1:

- **Status** — green dot + "All systems operational" (static; wired to `/api/admin/health` once #20 lands).
- **Changelog** — link to `#` (real changelog ships when there's content to point at).
- **Help / Contact support** — link to `#` (or `mailto:` if we want it functional now).
- **Collapse** — toggle button (already exists in #18 chrome; moves to bottom).

**Rationale.** Operator-side controls (status, support, changelog) don't belong in the nav and don't belong in the topbar. Bottom chrome is the Render convention.

### D6 — Active nav state uses brand colour, not neutral accent

Current AppShell uses `bg-accent text-accent-foreground` for active items — that reads as a hover/focus state, not an "active route" state. Switching to `bg-primary/10 text-primary` makes the active state distinctly branded. Hover keeps `bg-accent`.

**Rationale.** Visual disambiguation between "I'm hovering this" and "I'm here". Brand consistency.

### D7 — `/orgs/{slug}` is an Overview, not a quick-links page

Current page renders two quick-link cards (Projects, Members). Both are now in the sidebar — the cards are dead weight.

The Overview becomes:

```
┌─────────────────────────────────────────────┐
│ Overview                          [+ New ⌄] │
│                                             │
│ Projects                                    │
│ ┌───────┐ ┌───────┐ ┌───────┐ ┌─ ─ ─ ─┐    │
│ │ Proj1 │ │ Proj2 │ │ Proj3 │ │ + New│    │
│ └───────┘ └───────┘ └───────┘ └─ ─ ─ ─┘    │
└─────────────────────────────────────────────┘
```

Each project card is a clickable Link to `/orgs/{slug}/projects/{projectSlug}` showing name + slug + description.

The dashed `+ Create new project` tile uses the same dialog as the Projects page's "New project" button.

**Rationale.** Replace dead weight with actual data + the primary action.

### D8 — Section-label support is a prop, off by default for AppShell

Org-level dashboard has too few items (Projects + Settings) to warrant a UPPERCASE label. AdminShell will set labels (`OPERATIONS` / `CONFIGURATION`). `<Shell>` accepts a `label?: string` per section; when absent, only the nav items render.

**Rationale.** Same primitive, two consumers, no branching logic in the consumers.

## Risks / trade-offs

- **WorkspaceSwitcher in collapsed sidebar (`lg+` collapsed rail).** When collapsed, the switcher needs to render as just the avatar tile (no name, no chevron). On click, the dropdown still opens. Implementing this requires the switcher to know whether it's in collapsed mode — passed as a prop from the Sidebar. Manageable; documented in the component.
- **Topbar density at narrow widths.** Search + `+ New` + theme toggle + user menu = four controls. Below `lg`, the breadcrumb may need to truncate or hide; below `sm`, some controls move into a hamburger menu. v1 keeps it simple at `lg+` and lets shadcn's defaults handle smaller; revisit if mobile UX is prioritised.
- **`+ New` dropdown context.** "Create project" needs the active org slug. If the user is on `/orgs/new` (no active slug), the action is hidden. Handled by reading from `useOrgStore`.
- **Breadcrumb derivation from URL.** Single-segment is trivial (`Overview` / `Projects` / `Settings` / `Members` / `Branding`). For project detail (`/orgs/{slug}/projects/{projectSlug}`) it would ideally show `Projects / <project name>` — requires fetching the project name. v1 ships single-segment + raw projectSlug fallback; nicer breadcrumbs land in a follow-up.

## Migration plan

- All changes are frontend; no DB migrations.
- The codegen client doesn't change (no new endpoints).
- Existing dashboard routes (`/orgs/{slug}/...`) keep their URLs; only the surrounding chrome and the Overview content change.
- Closed PR #18 already shipped the foundation (AppShell, ThemeProvider, ThemePicker). This PR refactors the chrome subset.

## Open questions

- **Q: Should `+ New` dropdown be visible when the user has zero orgs?** Tentative: yes — "Create organisation" is still a valid action; "Create project" is hidden until an org is active.
- **Q: Theme mode toggle placement** — between Search and `+ New`, or in the user menu? Tentative: keep it inline (between `+ New` and user) so users can flip without opening a menu. Re-open if the topbar feels cluttered.
- **Q: Does the AdminShell need a workspace switcher at all?** No — admin is cross-org. The header slot in `<Shell>` for AdminShell is just a "PLATFORM ADMIN" pill. Already locked in #19's design.md D6.

## References

- Issue ganjasan/fastsaas#24.
- Issue ganjasan/fastsaas#5 archive `2026-05-05-theme-tokens-and-app-shell` — supplies the AppShell that this rebuilds.
- Issue ganjasan/fastsaas#19 — consumes the `<Shell>` primitive for AdminShell.
- ADR-012 (shadcn/ui canonical) — Render-style is implemented on top of shadcn primitives, no new deps.
- ADR-011 (frontend layout) — file-tree convention preserved.
