/**
 * End-to-end smoke for the multi-tenant happy path (issue #3 phase 11).
 *
 * Drives a real browser through:
 *   dev-bypass auth → list orgs (empty) → create org → create project →
 *   open project detail → relogin
 *
 * Uses `GET /auth/oauth/dev/start?email=...` (`OAUTH_DEV_BYPASS=true` in CI)
 * to obtain a fresh session without going through register + verify-email +
 * password login. The end-to-end auth flow including Mailhog is already
 * exhaustively covered by backend integration tests
 * (`backend/tests/test_api_auth.py`, `test_identity_email.py`); this e2e
 * focuses on the multi-tenant UI layer above the auth gate.
 *
 * After the dev-bypass GET sets the refresh httpOnly cookie, navigating to
 * /orgs causes the SPA's first request to 401 → `recoverFrom401` swaps the
 * cookie for a fresh access token → the listing renders. So the test never
 * needs to inject a token into the SPA's in-memory store directly.
 */
import { type APIRequestContext, expect, test } from "@playwright/test";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function devBypassLogin(req: APIRequestContext, email: string): Promise<void> {
  // GET goes through Vite's same-origin proxy to the backend at
  // /auth/oauth/dev/start; Set-Cookie response header lands the
  // httpOnly refresh cookie on the browser context.
  const res = await req.get(`/auth/oauth/dev/start?email=${encodeURIComponent(email)}`);
  expect(res.status(), `dev-bypass returned ${res.status()} ${await res.text()}`).toBe(200);
}

test.describe("multi-tenant smoke", () => {
  test("dev-bypass → create org+project → relogin", async ({ page }) => {
    const email = uniqueEmail("smoke");
    const orgSlug = `s-${Date.now().toString(36)}`;
    const projectSlug = `p-${Date.now().toString(36)}`;

    // ── Auth (dev-bypass) ───────────────────────────────────────────────
    await devBypassLogin(page.request, email);

    // First page load triggers a 401 on /orgs API call → recoverFrom401
    // exchanges the refresh cookie for an access token, retries, listing
    // renders empty-state.
    await page.goto("/orgs");
    await expect(page.getByRole("heading", { name: /welcome to fastsaas/i })).toBeVisible({
      timeout: 15_000,
    });

    // ── Create org ──────────────────────────────────────────────────────
    await page
      .getByRole("link", { name: /create organisation/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/orgs\/new$/);
    await page.getByLabel("Name").fill("Acme Co");
    await page.getByLabel("Slug").fill(orgSlug);
    await page.getByRole("button", { name: /create organisation/i }).click();

    await expect(page).toHaveURL(new RegExp(`/orgs/${orgSlug}$`), { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: "Acme Co" })).toBeVisible();

    // ── Create project ──────────────────────────────────────────────────
    await page.getByRole("link", { name: /open projects/i }).click();
    await expect(page).toHaveURL(new RegExp(`/orgs/${orgSlug}/projects$`));

    await page
      .getByRole("button", { name: /new project/i })
      .first()
      .click();
    await page.getByLabel("Name").fill("Q3 Forecast");
    await page.getByLabel("Slug").fill(projectSlug);
    await page.getByRole("button", { name: /^create$/i }).click();

    await expect(page.getByRole("link", { name: "Q3 Forecast" })).toBeVisible();

    await page.getByRole("link", { name: "Q3 Forecast" }).click();
    await expect(page).toHaveURL(new RegExp(`/orgs/${orgSlug}/projects/${projectSlug}$`));
    await expect(page.getByRole("heading", { name: "Q3 Forecast" })).toBeVisible();

    // ── Re-login ────────────────────────────────────────────────────────
    // Drop the refresh cookie + reload. Then dev-bypass again under the
    // same email — the actor already exists, so this exercises the
    // "second sign-in for an existing actor" path, not the registration
    // path. We confirm we land back on /orgs with the org we just made.
    await page.context().clearCookies();
    await devBypassLogin(page.request, email);
    await page.goto("/orgs");
    await expect(page.getByRole("link", { name: "Acme Co" })).toBeVisible({ timeout: 15_000 });
  });
});
