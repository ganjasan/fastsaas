import { beforeEach, describe, expect, test } from "vitest";

import { useUIStore } from "@/stores/uiStore";

describe("useUIStore", () => {
  beforeEach(() => {
    useUIStore.setState({ theme: "system", sidebarCollapsed: false });
  });

  test("toggleSidebar flips the collapsed state", () => {
    // GIVEN a fresh UI store with sidebar expanded
    expect(useUIStore.getState().sidebarCollapsed).toBe(false);

    // WHEN the sidebar is toggled
    useUIStore.getState().toggleSidebar();

    // THEN the collapsed state is true
    expect(useUIStore.getState().sidebarCollapsed).toBe(true);
  });

  test("setTheme updates the theme", () => {
    // GIVEN the default theme
    expect(useUIStore.getState().theme).toBe("system");

    // WHEN the theme is set to dark
    useUIStore.getState().setTheme("dark");

    // THEN the theme reflects the change
    expect(useUIStore.getState().theme).toBe("dark");
  });
});
