import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  retries: process.env.CI ? 2 : 0,
  reporter: process.env.CI ? "github" : "list",
  // FastSaaS host-port convention: Vite on :5273 (+100 shift) so several
  // SaaS-stack projects coexist on one workstation.
  use: {
    baseURL: "http://localhost:5273",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5273",
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
