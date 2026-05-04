/**
 * End-to-end smoke for the multi-tenant happy path (issue #3 phase 11).
 *
 * Drives a real browser through:
 *   dev-bypass auth → list orgs (empty) → create org → create project →
 *   open project detail → relogin
 *
 * Auth: `GET /auth/oauth/dev/start?email=...` (`OAUTH_DEV_BYPASS=true` in
 * CI) issues an access token + sets the refresh httpOnly cookie. We push
 * the access token into the SPA's auth store directly via the DEV-only
 * `window.__authStore` shim and SPA-navigate via
 * `window.__router.navigate(...)`. This avoids:
 *
 *   - the email + verify-email + login flow (already covered by backend
 *     integration tests; flaky to drive through a browser).
 *   - `page.goto("/orgs")` after auth, which is a full reload that
 *     would drop the in-memory access token (ADR-008 hybrid storage).
 */
import { type Page, expect, test } from "@playwright/test";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function devBypassAuth(page: Page, email: string): Promise<string> {
  const res = await page.request.get(`/auth/oauth/dev/start?email=${encodeURIComponent(email)}`);
  expect(res.status(), `dev-bypass returned ${res.status()} ${await res.text()}`).toBe(200);
  const body = (await res.json()) as { access_token: string };
  expect(body.access_token, "dev-bypass response missing access_token").toBeTruthy();
  return body.access_token;
}

/** Push the access token into the running SPA's Zustand auth store. */
async function injectAccessToken(page: Page, token: string): Promise<void> {
  await page.evaluate((t) => {
    type StoreRef = {
      __authStore?: { getState: () => { setAccessToken: (token: string) => void } };
    };
    const store = (window as unknown as StoreRef).__authStore;
    if (!store) throw new Error("__authStore is not exposed — DEV build expected");
    store.getState().setAccessToken(t);
  }, token);
}

/** SPA-navigate without a full reload via the DEV-exposed TanStack Router. */
async function spaNavigate(page: Page, to: string): Promise<void> {
  await page.evaluate((path) => {
    type RouterRef = {
      __router?: { navigate: (opts: { to: string }) => Promise<void> | void };
    };
    const router = (window as unknown as RouterRef).__router;
    if (!router) throw new Error("__router is not exposed — DEV build expected");
    return router.navigate({ to: path });
  }, to);
}

test.describe("multi-tenant smoke", () => {
  test("dev-bypass → create org+project → relogin", async ({ page }) => {
    const email = uniqueEmail("smoke");
    const orgSlug = `s-${Date.now().toString(36)}`;
    const projectSlug = `p-${Date.now().toString(36)}`;

    // ── Initial page load + auth ─────────────────────────────────────────
    // Land on a public page so the SPA boots and exposes the DEV shims,
    // then dev-bypass for tokens, then push the access token in.
    await page.goto("/auth/login");
    const accessToken = await devBypassAuth(page, email);
    await injectAccessToken(page, accessToken);

    // ── /orgs empty state ───────────────────────────────────────────────
    await spaNavigate(page, "/orgs");
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
    // Clear cookies + zero out the in-memory token, then dev-bypass under
    // the same email. Exercises the "second sign-in for an existing
    // actor" path; we confirm we can re-discover the org we just made.
    await page.context().clearCookies();
    await page.evaluate(() => {
      type StoreRef = {
        __authStore?: { getState: () => { clear: () => void } };
      };
      (window as unknown as StoreRef).__authStore?.getState?.().clear();
    });
    const accessToken2 = await devBypassAuth(page, email);
    await injectAccessToken(page, accessToken2);
    await spaNavigate(page, "/orgs");
    await expect(page.getByRole("link", { name: "Acme Co" })).toBeVisible({ timeout: 15_000 });
  });
});
