/**
 * Command palette open-state + per-workspace recent-searches.
 *
 * Recents persist via Zustand `persist` keyed by workspace slug so two
 * orgs in the same browser do not share each other's history (each
 * workspace's hits are a tenant-scoped surface; commingling them would
 * leak names across orgs in autocomplete).
 *
 * Recents are capped at MAX_RECENTS per workspace; older entries are
 * dropped. Recents store the full SearchHit so navigation + render can
 * happen without re-querying the backend.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { SearchHit } from "./types";

const MAX_RECENTS = 8;

interface SearchState {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;

  recentByWorkspace: Record<string, SearchHit[]>;
  recordRecent: (workspaceSlug: string, hit: SearchHit) => void;
  getRecents: (workspaceSlug: string) => SearchHit[];
  clearRecents: (workspaceSlug: string) => void;
}

export const useSearchStore = create<SearchState>()(
  persist(
    (set, get) => ({
      open: false,
      setOpen: (open) => set({ open }),
      toggle: () => set((s) => ({ open: !s.open })),

      recentByWorkspace: {},
      recordRecent: (workspaceSlug, hit) =>
        set((s) => {
          const prior = s.recentByWorkspace[workspaceSlug] ?? [];
          // Dedup by entity_type + entity_id; new entry floats to top.
          const filtered = prior.filter(
            (h) => !(h.entity_type === hit.entity_type && h.entity_id === hit.entity_id),
          );
          const next = [hit, ...filtered].slice(0, MAX_RECENTS);
          return {
            recentByWorkspace: { ...s.recentByWorkspace, [workspaceSlug]: next },
          };
        }),
      getRecents: (workspaceSlug) => get().recentByWorkspace[workspaceSlug] ?? [],
      clearRecents: (workspaceSlug) =>
        set((s) => {
          const { [workspaceSlug]: _, ...rest } = s.recentByWorkspace;
          return { recentByWorkspace: rest };
        }),
    }),
    {
      name: "fastsaas-search",
      // Don't persist `open` — reload should not re-open the palette.
      partialize: (s) => ({ recentByWorkspace: s.recentByWorkspace }),
    },
  ),
);
