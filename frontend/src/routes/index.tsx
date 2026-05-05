/**
 * `/` — root entry point.
 *
 * Redirects based on auth state:
 * - Unauthenticated → `/auth/login`.
 * - Authenticated → `/orgs` (the org-list page handles its own pin/empty
 *   state and forwards into the active org from there).
 *
 * The redirect runs in `beforeLoad` so the user never sees an intermediate
 * placeholder. The auth store is in-memory (per ADR-008 hybrid storage),
 * so the read here is synchronous — no flicker.
 */
import { createFileRoute, redirect } from "@tanstack/react-router";

import { useAuthStore } from "@/features/auth/lib/authStore";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    const token = useAuthStore.getState().accessToken;
    throw redirect({ to: token ? "/orgs" : "/auth/login" });
  },
});
