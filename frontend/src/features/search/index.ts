/**
 * Public surface of the frontend search foundation.
 *
 * Side effect: importing this module wires the foundation registrations
 * (project + member renderers, dashboard / projects / members pages).
 * Downstream features should `import "@/features/search";` once at
 * application bootstrap and then call `registerRenderer` /
 * `registerPage` / `registerAction` from their own feature modules.
 */
export type {
  ActionEntry,
  PageActionContext,
  PageEntry,
  SearchGroup,
  SearchHit,
  SearchResponse,
} from "./types";

export {
  type HitRenderer,
  type RendererProps,
  getRenderer,
  registerRenderer,
  renderHit,
} from "./registries/rendererRegistry";

export { actions, registerAction } from "./registries/actionsRegistry";
export { pages, registerPage } from "./registries/pagesRegistry";

export { useSearchStore } from "./searchStore";

import { registerPage } from "./registries/pagesRegistry";
import { registerRenderer } from "./registries/rendererRegistry";
import { MemberRenderer } from "./renderers/memberRenderer";
import { ProjectRenderer } from "./renderers/projectRenderer";

// Foundation renderers — register on import.
registerRenderer("project", ProjectRenderer);
registerRenderer("member", MemberRenderer);

// Foundation pages — workspace-scoped nav targets the palette
// surfaces without backend round-trips.
registerPage({
  id: "page:projects",
  label: "Projects",
  href: (slug) => `/orgs/${slug}/projects`,
  keywords: ["work", "items"],
  visible: (ctx) => ctx.shell === "app" && Boolean(ctx.workspaceSlug),
});

registerPage({
  id: "page:members",
  label: "Members",
  description: "Org directory",
  href: (slug) => `/orgs/${slug}/settings/members`,
  keywords: ["team", "people", "directory"],
  visible: (ctx) => ctx.shell === "app" && Boolean(ctx.workspaceSlug),
});

registerPage({
  id: "page:settings",
  label: "Workspace settings",
  href: (slug) => `/orgs/${slug}/settings`,
  keywords: ["org", "preferences"],
  visible: (ctx) => ctx.shell === "app" && Boolean(ctx.workspaceSlug),
});

// AdminShell pages.
registerPage({
  id: "page:admin-orgs",
  label: "All orgs",
  href: () => "/admin/orgs",
  keywords: ["organisations", "tenants"],
  visible: (ctx) => ctx.shell === "admin",
});

registerPage({
  id: "page:admin-metrics",
  label: "Platform metrics",
  href: () => "/admin/metrics",
  visible: (ctx) => ctx.shell === "admin",
});

registerPage({
  id: "page:admin-health",
  label: "Health checks",
  href: () => "/admin/health",
  visible: (ctx) => ctx.shell === "admin",
});

// No foundation actions in v1 — theme toggle / sign-out live on the
// topbar already, so adding them as palette actions would just
// duplicate paths. Downstream features can register their own.
