/**
 * ThemeProvider — applies the active org's preset + the user's mode pref to
 * `<html>` via inline CSS-var setters.
 *
 * Inputs:
 * - `org.theme.preset` (per-org, from `useGetOrg` once the active org slug
 *   is pinned via `useOrgStore`). Defaults to `default` for a fresh org.
 * - `org.theme.mode_default` (per-org, optional). Used when the user has
 *   not made an explicit choice.
 * - `useThemeStore.mode` (per-user, localStorage). Null means "inherit
 *   from org default".
 *
 * Outputs:
 * - For every key in `THEME_TOKENS`, sets `--{key}` on
 *   `document.documentElement.style`. Tailwind's `@theme inline` block in
 *   `theme.css` reads those vars to resolve utility classes like
 *   `bg-primary` and `border-border`.
 * - Toggles the `.dark` class on `<html>` when the resolved mode is dark
 *   (or `system` and `prefers-color-scheme: dark`).
 *
 * Live preview:
 * - The picker calls `useThemeContext().setPreviewPreset(p)` to override
 *   the active preset for the duration of a hover. Passing `null` reverts.
 */
import {
  type ReactNode,
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useGetOrgOrgsSlugGet } from "@/api/generated/orgs/orgs";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import { useThemeStore } from "@/features/theme/themeStore";
import {
  PRESETS,
  THEME_TOKENS,
  ThemeModeDefault,
  type ThemePreset,
  parseOrgTheme,
} from "@/lib/theme";

interface ThemeContextValue {
  /** Currently rendered preset (org's, or preview override). */
  activePreset: ThemePreset;
  /** Org's persisted preset, ignoring any preview. */
  persistedPreset: ThemePreset;
  /** Resolved mode (`light` | `dark`); `system` is collapsed already. */
  resolvedMode: "light" | "dark";
  /** User's stored mode pref. `null` means inherit from org default. */
  userMode: ThemeModeDefault | null;
  setUserMode: (mode: ThemeModeDefault | null) => void;
  /** Provisional preset override for hover-preview. `null` reverts. */
  setPreviewPreset: (preset: ThemePreset | null) => void;
}

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function useThemeContext(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (ctx === null) {
    throw new Error("useThemeContext must be used inside <ThemeProvider>");
  }
  return ctx;
}

/** Resolve `mode + system` to a concrete `light` | `dark`. */
function resolveSystemMode(mode: ThemeModeDefault): "light" | "dark" {
  if (mode === ThemeModeDefault.system) {
    if (typeof window === "undefined") return "light";
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return mode;
}

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps): ReactNode {
  const slug = useOrgStore((s) => s.currentOrgSlug);
  const userMode = useThemeStore((s) => s.mode);
  const setUserMode = useThemeStore((s) => s.setMode);

  // Org fetch is conditional on a pinned slug. Outside the dashboard
  // (`/login`, `/orgs/new`) the slug is null and we render with the
  // default preset.
  const { data: org } = useGetOrgOrgsSlugGet(slug ?? "", {
    query: { enabled: slug !== null },
  });

  const persistedTheme = useMemo(() => parseOrgTheme(org?.theme ?? {}), [org?.theme]);
  const persistedPreset = persistedTheme.preset;
  const orgModeDefault = persistedTheme.mode_default ?? ThemeModeDefault.system;
  const effectiveMode: ThemeModeDefault = userMode ?? orgModeDefault;

  const [previewPreset, setPreviewPreset] = useState<ThemePreset | null>(null);
  const activePreset = previewPreset ?? persistedPreset;

  // Track resolved mode so consumers (Topbar toggle UI) can show the
  // current rendered state even when mode is `system`.
  const [resolvedMode, setResolvedMode] = useState<"light" | "dark">(() =>
    resolveSystemMode(effectiveMode),
  );

  // Apply preset vars + dark class. Re-runs on every preset / mode change.
  useEffect(() => {
    const resolved = resolveSystemMode(effectiveMode);
    setResolvedMode(resolved);

    const vars = PRESETS[activePreset][resolved];
    const root = document.documentElement;
    for (const key of THEME_TOKENS) {
      root.style.setProperty(`--${key}`, vars[key]);
    }
    root.classList.toggle("dark", resolved === "dark");
  }, [activePreset, effectiveMode]);

  // Subscribe to OS-level dark-mode changes when mode is `system`.
  useEffect(() => {
    if (effectiveMode !== ThemeModeDefault.system) return;
    if (typeof window === "undefined") return;

    const mql = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (): void => {
      const resolved = mql.matches ? "dark" : "light";
      setResolvedMode(resolved);
      const vars = PRESETS[activePreset][resolved];
      const root = document.documentElement;
      for (const key of THEME_TOKENS) {
        root.style.setProperty(`--${key}`, vars[key]);
      }
      root.classList.toggle("dark", resolved === "dark");
    };
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [activePreset, effectiveMode]);

  const setPreviewPresetCb = useCallback((preset: ThemePreset | null) => {
    setPreviewPreset(preset);
  }, []);

  const value: ThemeContextValue = useMemo(
    () => ({
      activePreset,
      persistedPreset,
      resolvedMode,
      userMode,
      setUserMode,
      setPreviewPreset: setPreviewPresetCb,
    }),
    [activePreset, persistedPreset, resolvedMode, userMode, setUserMode, setPreviewPresetCb],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
