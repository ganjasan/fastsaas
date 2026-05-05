/**
 * Unit tests for `useThemeStore` — verifies the per-user mode pref
 * persists to localStorage under `fastsaas.theme` and round-trips cleanly.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ThemeModeDefault } from "@/lib/theme";

import { useThemeStore } from "./themeStore";

describe("useThemeStore", () => {
  beforeEach(() => {
    useThemeStore.setState({ mode: null });
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.clear();
    }
  });

  afterEach(() => {
    useThemeStore.setState({ mode: null });
  });

  it("starts with null mode (inherit org default)", () => {
    // GIVEN a fresh store
    // WHEN we read mode
    // THEN it is null — meaning "fall back to org default"
    expect(useThemeStore.getState().mode).toBeNull();
  });

  it("setMode persists the user's explicit choice", () => {
    // GIVEN a fresh store
    // WHEN setMode("dark") is called
    useThemeStore.getState().setMode(ThemeModeDefault.dark);
    // THEN the store reflects it AND localStorage carries the persisted record
    expect(useThemeStore.getState().mode).toBe(ThemeModeDefault.dark);
    const persisted = window.localStorage.getItem("fastsaas.theme");
    expect(persisted).toContain("dark");
  });

  it("setMode(null) resets to inherit", () => {
    // GIVEN a user who toggled to dark
    useThemeStore.getState().setMode(ThemeModeDefault.dark);
    // WHEN they reset
    useThemeStore.getState().setMode(null);
    // THEN the store goes back to null — and the topbar will show the org default
    expect(useThemeStore.getState().mode).toBeNull();
  });
});
