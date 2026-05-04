/**
 * Pinned-org store. Persists `currentOrgSlug` to localStorage so a tab
 * reload doesn't dump the user back to the org switcher.
 *
 * The store also exposes an imperative shim for the orval mutator
 * (`api/client.ts`), which runs outside React and needs the slug at
 * request-build time to populate the `X-Org` header — see
 * `tenants/dependencies.py::tenant_context`.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

interface OrgState {
  currentOrgSlug: string | null;
  setCurrentOrgSlug: (slug: string | null) => void;
}

export const useOrgStore = create<OrgState>()(
  persist(
    (set) => ({
      currentOrgSlug: null,
      setCurrentOrgSlug: (slug) => set({ currentOrgSlug: slug }),
    }),
    { name: "fastsaas.org" },
  ),
);

/** Imperative shim for non-React callers (orval mutator). */
export const orgPin = {
  get: (): string | null => useOrgStore.getState().currentOrgSlug,
  set: (slug: string | null): void => useOrgStore.getState().setCurrentOrgSlug(slug),
};
