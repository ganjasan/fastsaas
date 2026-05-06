/**
 * Frontend mirror of `fastsaas.search.models` — kept hand-written rather
 * than orval-generated so the palette can use them in places (recent
 * searches store, renderer registry) that the generated client never
 * touches. The shape is intentionally identical to the API response.
 */

export interface SearchHit {
  entity_type: string;
  entity_id: string;
  title: string;
  subtitle?: string | null;
  href: string;
}

export interface SearchGroup {
  entity_type: string;
  label: string;
  hits: SearchHit[];
}

export interface SearchResponse {
  query: string;
  groups: SearchGroup[];
}

/**
 * Local-only result kinds the palette renders without ever talking to
 * the backend. Pages and Actions live entirely in the frontend
 * registries — see `pagesRegistry.ts` and `actionsRegistry.ts`.
 */
export interface PageEntry {
  id: string;
  label: string;
  /** Optional secondary line under `label`. */
  description?: string;
  /**
   * Function returning the destination href. Receives the active
   * workspace slug so workspace-scoped pages don't need their own slug
   * lookup at registration time.
   */
  href: (workspaceSlug: string) => string;
  /**
   * Optional keyword tokens beyond `label` to widen the cmdk fuzzy
   * match — e.g. ["team", "people"] for the Members page.
   */
  keywords?: string[];
  /**
   * Visibility predicate. Defaults to "always show". Receives the
   * active workspace slug + a predicate the caller pre-computed
   * (e.g. is the user an admin?).
   */
  visible?: (ctx: PageActionContext) => boolean;
}

export interface ActionEntry {
  id: string;
  label: string;
  description?: string;
  /** Side-effecting handler. Returning a Promise keeps the palette
   * open until the action resolves; it's then closed automatically. */
  perform: (ctx: PageActionContext) => void | Promise<void>;
  keywords?: string[];
  visible?: (ctx: PageActionContext) => boolean;
}

export interface PageActionContext {
  workspaceSlug: string;
  /** True inside `<AdminShell>` (platform-staff palette); false in
   * `<AppShell>`. Lets pages/actions tailor their visibility per shell. */
  shell: "app" | "admin";
}
