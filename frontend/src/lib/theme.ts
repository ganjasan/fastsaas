/**
 * Theme tokens — Phase 1 of ADR-012.
 *
 * Each preset declares a complete CSS-variable set covering every token in
 * `frontend/src/styles/theme.css`. Each preset has two sub-sets (`light`,
 * `dark`) so the per-user mode toggle is orthogonal to the per-org brand
 * choice. The active preset's vars are applied to `<html>` via
 * `<ThemeProvider>` (see `frontend/src/features/theme/ThemeProvider.tsx`).
 *
 * Phase 2 (separate epic) will add a free-form theme editor; until then the
 * wire contract `Organisation.theme` is constrained to one of these five
 * presets via `ThemePreset` (mirrored on the backend in
 * `tenants/schemas.py::ThemePreset`).
 */

import { z } from "zod";

import { ThemeModeDefault, ThemePreset } from "@/api/generated/fastSaaS.schemas";

export { ThemeModeDefault, ThemePreset };

// CSS-variable keys (without the leading `--`). Mirrors the contract in
// `styles/theme.css` and the design-system spec.
export const THEME_TOKENS = [
  "background",
  "foreground",
  "card",
  "card-foreground",
  "popover",
  "popover-foreground",
  "primary",
  "primary-foreground",
  "secondary",
  "secondary-foreground",
  "muted",
  "muted-foreground",
  "accent",
  "accent-foreground",
  "destructive",
  "destructive-foreground",
  "border",
  "input",
  "ring",
  "radius",
] as const;

export type ThemeToken = (typeof THEME_TOKENS)[number];
export type ThemeVarMap = Record<ThemeToken, string>;

/** Each preset ships a `light` + `dark` var pair. The user's mode toggle
 * picks between them; the org's preset choice picks which preset is active. */
export interface ThemePresetSpec {
  light: ThemeVarMap;
  dark: ThemeVarMap;
}

// HSL values are stored without the `hsl()` wrapper to match Tailwind v4's
// `@theme inline` usage of `hsl(var(--background))` in `theme.css`. `radius`
// is the lone non-HSL value.

const DEFAULT: ThemePresetSpec = {
  light: {
    background: "0 0% 100%",
    foreground: "240 10% 3.9%",
    card: "0 0% 100%",
    "card-foreground": "240 10% 3.9%",
    popover: "0 0% 100%",
    "popover-foreground": "240 10% 3.9%",
    primary: "240 5.9% 10%",
    "primary-foreground": "0 0% 98%",
    secondary: "240 4.8% 95.9%",
    "secondary-foreground": "240 5.9% 10%",
    muted: "240 4.8% 95.9%",
    "muted-foreground": "240 3.8% 46.1%",
    accent: "240 4.8% 95.9%",
    "accent-foreground": "240 5.9% 10%",
    destructive: "0 84.2% 60.2%",
    "destructive-foreground": "0 0% 98%",
    border: "240 5.9% 90%",
    input: "240 5.9% 90%",
    ring: "240 5.9% 10%",
    radius: "0.5rem",
  },
  dark: {
    background: "240 10% 3.9%",
    foreground: "0 0% 98%",
    card: "240 10% 3.9%",
    "card-foreground": "0 0% 98%",
    popover: "240 10% 3.9%",
    "popover-foreground": "0 0% 98%",
    primary: "0 0% 98%",
    "primary-foreground": "240 5.9% 10%",
    secondary: "240 3.7% 15.9%",
    "secondary-foreground": "0 0% 98%",
    muted: "240 3.7% 15.9%",
    "muted-foreground": "240 5% 64.9%",
    accent: "240 3.7% 15.9%",
    "accent-foreground": "0 0% 98%",
    destructive: "0 62.8% 30.6%",
    "destructive-foreground": "0 0% 98%",
    border: "240 3.7% 15.9%",
    input: "240 3.7% 15.9%",
    ring: "240 4.9% 83.9%",
    radius: "0.5rem",
  },
};

// Modern — softer rounded corners, blue-violet primary.
const MODERN: ThemePresetSpec = {
  light: {
    ...DEFAULT.light,
    primary: "262 83% 58%",
    "primary-foreground": "0 0% 100%",
    ring: "262 83% 58%",
    radius: "0.75rem",
  },
  dark: {
    ...DEFAULT.dark,
    primary: "263 70% 65%",
    "primary-foreground": "240 10% 3.9%",
    ring: "263 70% 65%",
    radius: "0.75rem",
  },
};

// Corporate — navy primary, sharper corners, professional feel.
const CORPORATE: ThemePresetSpec = {
  light: {
    ...DEFAULT.light,
    primary: "221 83% 26%",
    "primary-foreground": "0 0% 100%",
    accent: "221 70% 92%",
    "accent-foreground": "221 83% 26%",
    ring: "221 83% 26%",
    radius: "0.25rem",
  },
  dark: {
    ...DEFAULT.dark,
    primary: "221 75% 70%",
    "primary-foreground": "221 83% 10%",
    accent: "221 30% 22%",
    "accent-foreground": "221 75% 90%",
    ring: "221 75% 70%",
    radius: "0.25rem",
  },
};

// Dark — permanently dark regardless of mode toggle. The `light` set is a
// muted dark (lower contrast) so a user who explicitly forces light mode
// still sees a coherent dark-themed surface, just one notch less aggressive.
const DARK: ThemePresetSpec = {
  light: {
    background: "240 8% 12%",
    foreground: "0 0% 96%",
    card: "240 8% 14%",
    "card-foreground": "0 0% 96%",
    popover: "240 8% 14%",
    "popover-foreground": "0 0% 96%",
    primary: "0 0% 96%",
    "primary-foreground": "240 8% 12%",
    secondary: "240 5% 22%",
    "secondary-foreground": "0 0% 96%",
    muted: "240 5% 22%",
    "muted-foreground": "240 4% 65%",
    accent: "240 5% 22%",
    "accent-foreground": "0 0% 96%",
    destructive: "0 62% 50%",
    "destructive-foreground": "0 0% 100%",
    border: "240 5% 22%",
    input: "240 5% 22%",
    ring: "240 4% 80%",
    radius: "0.5rem",
  },
  dark: {
    ...DEFAULT.dark,
  },
};

// High-contrast — pure black/white extremes for accessibility (WCAG AAA).
const HIGH_CONTRAST: ThemePresetSpec = {
  light: {
    background: "0 0% 100%",
    foreground: "0 0% 0%",
    card: "0 0% 100%",
    "card-foreground": "0 0% 0%",
    popover: "0 0% 100%",
    "popover-foreground": "0 0% 0%",
    primary: "0 0% 0%",
    "primary-foreground": "0 0% 100%",
    secondary: "0 0% 92%",
    "secondary-foreground": "0 0% 0%",
    muted: "0 0% 92%",
    "muted-foreground": "0 0% 20%",
    accent: "0 0% 0%",
    "accent-foreground": "0 0% 100%",
    destructive: "0 100% 35%",
    "destructive-foreground": "0 0% 100%",
    border: "0 0% 0%",
    input: "0 0% 0%",
    ring: "0 0% 0%",
    radius: "0.125rem",
  },
  dark: {
    background: "0 0% 0%",
    foreground: "0 0% 100%",
    card: "0 0% 0%",
    "card-foreground": "0 0% 100%",
    popover: "0 0% 0%",
    "popover-foreground": "0 0% 100%",
    primary: "0 0% 100%",
    "primary-foreground": "0 0% 0%",
    secondary: "0 0% 12%",
    "secondary-foreground": "0 0% 100%",
    muted: "0 0% 12%",
    "muted-foreground": "0 0% 80%",
    accent: "0 0% 100%",
    "accent-foreground": "0 0% 0%",
    destructive: "0 100% 65%",
    "destructive-foreground": "0 0% 0%",
    border: "0 0% 100%",
    input: "0 0% 100%",
    ring: "0 0% 100%",
    radius: "0.125rem",
  },
};

export const PRESETS: Record<ThemePreset, ThemePresetSpec> = {
  default: DEFAULT,
  modern: MODERN,
  corporate: CORPORATE,
  dark: DARK,
  "high-contrast": HIGH_CONTRAST,
};

/** Display labels for each preset (shown in the picker UI). */
export const PRESET_LABELS: Record<ThemePreset, string> = {
  default: "Default",
  modern: "Modern",
  corporate: "Corporate",
  dark: "Dark",
  "high-contrast": "High contrast",
};

/** Wire-format Zod schema for `Organisation.theme` JSONB. Mirrors backend
 * `OrgThemeUpdateRequest` so a malformed value from the DB (e.g. legacy row
 * without a preset) falls back to `default` rather than crashing the app. */
export const orgThemeSchema = z
  .object({
    preset: z.nativeEnum(ThemePreset),
    mode_default: z.nativeEnum(ThemeModeDefault).optional(),
  })
  .strict();

export type OrgTheme = z.infer<typeof orgThemeSchema>;

/** Defensive parse: an org row with `theme = {}` or a legacy/unknown preset
 * resolves to `{preset: default}`. Never throws. */
export function parseOrgTheme(raw: unknown): OrgTheme {
  const result = orgThemeSchema.safeParse(raw);
  if (result.success) return result.data;
  return { preset: ThemePreset.default };
}
