/**
 * Unit tests for the preset map + Zod schema.
 *
 * No DOM, no network. Verifies that:
 * - the preset map is exhaustive (every preset has every token, both
 *   light and dark);
 * - the Zod schema accepts the 5 preset names + rejects unknowns;
 * - `parseOrgTheme` falls back gracefully for legacy / malformed rows.
 */
import { describe, expect, it } from "vitest";

import { PRESETS, THEME_TOKENS, ThemePreset, orgThemeSchema, parseOrgTheme } from "./theme";

describe("PRESETS map", () => {
  it.each(Object.values(ThemePreset))(
    "preset %s declares every token in both light and dark",
    (preset) => {
      // GIVEN a preset
      const spec = PRESETS[preset];
      // WHEN we enumerate the token contract
      // THEN every token is present in both light and dark
      for (const token of THEME_TOKENS) {
        expect(spec.light[token], `${preset}.light.${token}`).toBeTruthy();
        expect(spec.dark[token], `${preset}.dark.${token}`).toBeTruthy();
      }
    },
  );
});

describe("orgThemeSchema", () => {
  it.each(Object.values(ThemePreset))("accepts %s preset", (preset) => {
    // GIVEN a body with a known preset
    // WHEN parsed
    // THEN it succeeds
    expect(orgThemeSchema.safeParse({ preset }).success).toBe(true);
  });

  it("rejects an unknown preset", () => {
    // GIVEN a body with a fake preset
    // WHEN parsed
    // THEN it fails
    const r = orgThemeSchema.safeParse({ preset: "neon" });
    expect(r.success).toBe(false);
  });

  it("rejects extra fields (extra=forbid)", () => {
    // GIVEN a body with an extra key
    // WHEN parsed
    // THEN it fails — the wire contract is locked
    const r = orgThemeSchema.safeParse({
      preset: ThemePreset.default,
      primary: "#abc",
    });
    expect(r.success).toBe(false);
  });
});

describe("parseOrgTheme", () => {
  it("falls back to default preset on empty input", () => {
    // GIVEN an empty theme JSONB (legacy row pre-Phase-1)
    // WHEN parsed
    // THEN we get the `default` preset, no exception
    expect(parseOrgTheme({})).toEqual({ preset: ThemePreset.default });
  });

  it("falls back to default on malformed input", () => {
    // GIVEN a row with a malformed preset
    // WHEN parsed
    // THEN we still resolve to `default` rather than crashing the dashboard
    expect(parseOrgTheme({ preset: "neon" })).toEqual({
      preset: ThemePreset.default,
    });
  });

  it("preserves a valid preset + mode_default", () => {
    // GIVEN a row with both fields set
    // WHEN parsed
    // THEN both are returned untouched
    expect(parseOrgTheme({ preset: "corporate", mode_default: "dark" })).toEqual({
      preset: ThemePreset.corporate,
      mode_default: "dark",
    });
  });
});
