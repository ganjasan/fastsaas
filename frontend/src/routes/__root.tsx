import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, createRootRoute } from "@tanstack/react-router";

import { useAuthStore } from "@/features/auth/lib/authStore";
import { refreshAccessToken } from "@/features/auth/lib/refreshFlow";
import { ThemeProvider } from "@/features/theme/ThemeProvider";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

// Boot-time refresh gate. Per ADR-008 hybrid storage the access token is
// in-memory only — gone on every reload. The refresh cookie survives, so
// on app boot we attempt one `POST /auth/refresh`. If the cookie is valid
// the user lands silently in the dashboard; if it's expired or absent
// the access token stays null and the route redirects (`/` → /auth/login).
//
// Module-level flag so this fires exactly once per app mount: TanStack
// router calls `beforeLoad` again on every client-side navigation, but
// only the first one needs to consult the refresh endpoint.
let bootRefreshAttempted = false;

async function bootRefresh(): Promise<void> {
  if (bootRefreshAttempted) return;
  bootRefreshAttempted = true;
  if (useAuthStore.getState().accessToken !== null) return;
  const token = await refreshAccessToken();
  if (token !== null) {
    useAuthStore.getState().setAccessToken(token);
  }
}

export const Route = createRootRoute({
  beforeLoad: bootRefresh,
  component: () => (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <Outlet />
      </ThemeProvider>
    </QueryClientProvider>
  ),
});
