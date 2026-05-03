import { expect, test } from "@playwright/test";

test("home page loads", async ({ page }) => {
  // GIVEN a freshly-started dev server
  // WHEN navigating to the root
  await page.goto("/");

  // THEN the platform heading is visible
  await expect(page.getByRole("heading", { name: "FastSaaS" })).toBeVisible();
});
