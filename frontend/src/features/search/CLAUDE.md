# CLAUDE.md — `features/search/`

Frontend half of the search foundation. Mirrors the backend's
`SearchProvider` registry: each new domain entity that wants to appear
in the ⌘K palette ships **two** registrations — a backend
`SearchProvider` (see `backend/src/fastsaas/search/CLAUDE.md`) and a
frontend renderer.

If you add a backend provider but skip the frontend renderer, the
palette still shows your hits but with a generic fallback row + a
console warning. That's a soft signal of the gap; fix it by registering
a renderer.

## What lives here

| File | Role |
|---|---|
| `index.ts` | Public surface + foundation registrations (project + member renderers, AppShell/AdminShell pages). |
| `searchStore.ts` | Zustand store: palette `open` state + per-workspace recent searches. |
| `types.ts` | Hand-written mirror of the backend's `SearchHit/SearchGroup/SearchResponse` plus `PageEntry`/`ActionEntry`. |
| `registries/rendererRegistry.tsx` | `entity_type → React component` map. Default fallback handles unknown types. |
| `registries/pagesRegistry.ts` | Local nav targets (no backend round-trip). |
| `registries/actionsRegistry.ts` | Local side-effecting commands (no backend round-trip). |
| `renderers/*.tsx` | Foundation row renderers — project + member. |
| `components/CommandPalette.tsx` | The dialog. Composes pages + actions + recent searches + backend hits. |
| `components/CommandPaletteHotkey.tsx` | Window-level Cmd/Ctrl+K listener. Mounted by AppShell + AdminShell. |
| `hooks/useDebouncedValue.ts` | 180ms debounce on the input → backend query. |

## Recipes

### Add a renderer for a new entity type

```tsx
// In your downstream feature module:
// frontend/src/features/scenarios/index.ts
import { registerRenderer } from "@/features/search";
import { ScenarioRenderer } from "./ScenarioRenderer";

registerRenderer("scenario", ScenarioRenderer);
```

```tsx
// frontend/src/features/scenarios/ScenarioRenderer.tsx
import { Activity } from "lucide-react";
import type { ReactNode } from "react";
import type { RendererProps } from "@/features/search";

export function ScenarioRenderer({ hit }: RendererProps): ReactNode {
  return (
    <>
      <Activity className="h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-sm">{hit.title}</span>
        {hit.subtitle ? (
          <span className="truncate text-xs text-muted-foreground">
            {hit.subtitle}
          </span>
        ) : null}
      </div>
    </>
  );
}
```

Then make sure your feature's `index.ts` is imported once at app
bootstrap (typically via the route file that uses it). The renderer
registry is process-global; one import is enough.

### Add a Page (no backend round-trip)

Pages are nav targets the palette surfaces under "Pages". Use them
when a route exists but the user might not know its URL.

```ts
import { registerPage } from "@/features/search";

registerPage({
  id: "page:scenarios",
  label: "Scenarios",
  description: "Run and review scenarios",
  href: (slug) => `/orgs/${slug}/scenarios`,
  keywords: ["simulate", "model run"],
  visible: (ctx) => ctx.shell === "app" && Boolean(ctx.workspaceSlug),
});
```

`href` receives the active workspace slug; `visible(ctx)` controls per-
shell display (the same module can register an AppShell page and an
AdminShell page side-by-side).

### Add an Action (palette command)

Actions perform a side effect (open a dialog, toggle a setting, copy
something). Keep them rare — most "things to do" live on the page
they belong to.

```ts
import { registerAction } from "@/features/search";

registerAction({
  id: "action:invite-member",
  label: "Invite member…",
  description: "Send an org invitation",
  keywords: ["new", "team"],
  perform: ({ workspaceSlug }) => {
    inviteDialog.open(workspaceSlug);
  },
  visible: (ctx) => ctx.shell === "app",
});
```

`perform` may return a Promise — the palette stays open until it
resolves and then closes automatically.

## Conventions

- **One renderer per `entity_type`.** Same fail-loud contract as the
  backend: `registerRenderer` throws on duplicate keys.
- **Renderers are thin.** A row is icon + title + subtitle. No links,
  no buttons, no badges that hijack focus — selection is a single
  cmdk action and the palette closes.
- **Hrefs come from the backend.** `SearchHit.href` is server-rendered
  so the frontend never needs entity-aware URL knowledge. Renderers
  read `hit.title` / `hit.subtitle` only; the wrapping `CommandItem`
  handles navigation.
- **Don't filter rows in renderers.** The backend already filters by
  capability; the palette already filters by query. Renderers always
  render the row they're given.
- **Import `@/features/search` for side effects** at any shell that
  needs the foundation registrations. Both AppShell and AdminShell
  already do this; downstream features only need to ensure their
  `index.ts` runs.

## What NOT to do

- **Do NOT call `register*` from a render function or `useEffect`.**
  Registration is at module-load. Calling it during render runs it
  multiple times (StrictMode double-mount → duplicate-key throw).
- **Do NOT bypass the backend `SearchProvider` and fetch directly.**
  The palette is the only place the search response lives. If a domain
  needs a per-page "search inside this list" UI, that's a separate
  component on its own data path — the palette doesn't replace it.
- **Do NOT mutate `SearchHit.href`** before navigation. The backend
  built it intentionally with the right slug + query string.
- **Do NOT cache search results outside TanStack Query.** The
  generated client already de-dupes in-flight requests and respects
  AbortSignal. A second cache layer just creates staleness bugs.
- **Do NOT render user-controlled strings via raw-HTML props** —
  always render strings as text children so React's text-content
  escaping handles them. Raw-HTML rendering is the one path that turns
  arbitrary `<script>` content from the backend into live DOM.
