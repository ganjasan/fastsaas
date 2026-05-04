/**
 * End-to-end smoke for the multi-tenant happy path (issue #3 phase 11).
 *
 * Drives a real browser through the full UC chain:
 *   register → consume verification mail → login → create org →
 *   create project → log out → log in again → land on /orgs.
 *
 * Mailhog HTTP API URL is `MAILHOG_HTTP_URL` (defaults to :8025 for CI;
 * the dev stack maps it to :8125 per the +100 host-port shift).
 *
 * Backend / frontend are reached through Vite's same-origin proxy
 * (`/auth/*`, `/orgs*`), so the test only ever talks to baseURL
 * (5273 locally, 5273 in CI when run via the bundled webServer).
 */
import { type APIRequestContext, expect, test } from "@playwright/test";

const MAILHOG_HTTP_URL = process.env.MAILHOG_HTTP_URL ?? "http://localhost:8025";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

async function clearMailhog(req: APIRequestContext): Promise<void> {
  await req.delete(`${MAILHOG_HTTP_URL}/api/v1/messages`);
}

async function fetchVerifyTokenFor(req: APIRequestContext, email: string): Promise<string> {
  // Poll Mailhog briefly — SMTP delivery is sub-second but BackgroundTasks
  // mean the response can return before the mail lands.
  for (let i = 0; i < 30; i++) {
    const res = await req.get(`${MAILHOG_HTTP_URL}/api/v2/messages`);
    if (res.ok()) {
      const body = await res.json();
      const message = body.items?.find(
        (m: { Content: { Headers: { To?: string[] } } }) =>
          m.Content.Headers.To?.[0]?.toLowerCase() === email.toLowerCase(),
      );
      if (message) {
        const decoded = Buffer.from(message.Content.Body as string, "binary").toString("utf8");
        const link = decoded.match(/https?:\/\/[^\s"<>]+\/auth\/verify-email\/([^\s"<>]+)/);
        if (link?.[1]) return link[1];
      }
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`No verification email arrived for ${email} within 7.5s`);
}

test.describe("multi-tenant smoke", () => {
  test("register → verify → create org+project → relogin", async ({ page, request }) => {
    await clearMailhog(request);

    const email = uniqueEmail("smoke");
    const password = "correct horse battery staple";
    const orgSlug = `s-${Date.now().toString(36)}`;
    const projectSlug = `p-${Date.now().toString(36)}`;

    // ── Register ────────────────────────────────────────────────────────
    await page.goto("/auth/register");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /create account|sign up|register/i }).click();

    // The register page transitions to a "check your email" state OR the
    // verify-email landing once consumed; we don't depend on the exact
    // copy, just on having picked up the verification token.
    const verifyToken = await fetchVerifyTokenFor(request, email);

    await page.goto(`/auth/verify-email/${verifyToken}`);
    // Wait for the verify mutation to settle — the page transitions from
    // "Verifying…" to "Email verified" once the side effect commits. We
    // *need* that commit before login; without it, /auth/login still
    // 403s with auth.email_unverified.
    await expect(page.getByRole("heading", { name: /email verified/i })).toBeVisible({
      timeout: 15_000,
    });

    // ── Login ───────────────────────────────────────────────────────────
    await page.goto("/auth/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();

    // Login SPA-navigates to /orgs; full `page.goto` would reload and
    // drop the in-memory access token (ADR-008 hybrid storage). 15s
    // generous timeout — CI runners are slower than local.
    await page.waitForURL(/\/orgs\/?$/, { timeout: 15_000 });
    await expect(page.getByRole("heading", { name: /welcome to fastsaas/i })).toBeVisible();

    // ── Create org ──────────────────────────────────────────────────────
    await page
      .getByRole("link", { name: /create organisation/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/orgs\/new$/);
    await page.getByLabel("Name").fill("Acme Co");
    await page.getByLabel("Slug").fill(orgSlug);
    await page.getByRole("button", { name: /create organisation/i }).click();

    await expect(page).toHaveURL(new RegExp(`/orgs/${orgSlug}$`));
    await expect(page.getByRole("heading", { name: "Acme Co" })).toBeVisible();

    // ── Create project ──────────────────────────────────────────────────
    await page.getByRole("link", { name: /open projects/i }).click();
    await expect(page).toHaveURL(new RegExp(`/orgs/${orgSlug}/projects$`));

    // Empty state has a "New project" button; click it to open the dialog.
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

    // ── Log out + log back in ───────────────────────────────────────────
    // No dedicated logout button on the placeholder shell yet; clear the
    // in-memory access token by reloading the SPA after evicting it from
    // the Zustand store via the public hook surface, then sign in again.
    await page.evaluate(() => {
      // The store hook's `clear()` is the canonical way to drop the access
      // token; localStorage holds only the org-pin slug, never the token.
      // biome-ignore lint/suspicious/noExplicitAny: page-context type lift
      (window as any).__authStore?.getState?.().clear?.();
    });
    await page.context().clearCookies();
    await page.goto("/auth/login");
    await page.getByLabel("Email").fill(email);
    await page.getByLabel("Password").fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();

    await page.waitForURL(/\/orgs\/?$/, { timeout: 15_000 });
    await expect(page.getByRole("link", { name: "Acme Co" })).toBeVisible();
  });
});
