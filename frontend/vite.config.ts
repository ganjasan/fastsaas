import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// `.env` lives one level up (workspace root); both backend pydantic-settings
// and Vite read the same file so dev-config drift is impossible.
const ENV_DIR = "..";
const DEFAULT_API = "http://localhost:8000";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ENV_DIR, "");
  const apiBase = env.VITE_API_BASE_URL ?? DEFAULT_API;

  return {
    envDir: ENV_DIR,
    plugins: [
      TanStackRouterVite({ target: "react", autoCodeSplitting: true }),
      react(),
      tailwindcss(),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        // Same-origin proxy keeps the refresh httpOnly cookie working in dev.
        "/api": { target: apiBase, changeOrigin: true },
        // /auth/* is shared: the FE renders pages at /auth/login etc., AND
        // the backend exposes JSON endpoints at /auth/login etc. Distinguish
        // by Accept: navigation requests (text/html) fall through to Vite's
        // SPA index; XHR / fetch (application/json or */*) get proxied.
        "/auth": {
          target: apiBase,
          changeOrigin: true,
          bypass(req) {
            if (req.headers.accept?.includes("text/html")) return req.url;
          },
        },
      },
    },
  };
});
