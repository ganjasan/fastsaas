/**
 * Per-user theme-mode store. The user's preference (light / dark / system)
 * is persisted to localStorage under `fastsaas.theme`. Orthogonal to the
 * per-org `theme.preset` (which lives in `organisations.theme` JSONB and
 * is fetched via `useGetOrg`).
 *
 * On first load with no entry, the resolved mode falls back to the active
 * org's `theme.mode_default` (computed inside `<ThemeProvider>`); the store
 * itself stays null until the user explicitly toggles.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { ThemeModeDefault } from "@/lib/theme";

type Mode = ThemeModeDefault;

interface ThemeState {
  /** User's explicit choice. `null` means "inherit from org default". */
  mode: Mode | null;
  setMode: (mode: Mode | null) => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      mode: null,
      setMode: (mode) => set({ mode }),
    }),
    { name: "fastsaas.theme" },
  ),
);
