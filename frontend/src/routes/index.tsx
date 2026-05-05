/**
 * `/` — root entry point.
 *
 * Redirect ladder:
 * - No access token → `/auth/login`.
 * - Has token + pinned org slug from a previous session → `/orgs/{slug}`
 *   (lands the user in the dashboard they last used; if the slug is no
 *   longer accessible, the org-fetch on that route will 404 and the user
 *   can navigate to the org list manually).
 * - Has token but no pinned slug → `/orgs` (org list / empty-state).
 *
 * The redirect runs in `beforeLoad`. The auth store is in-memory and the
 * org store reads localStorage synchronously, so neither call blocks.
 */
import { createFileRoute, redirect } from "@tanstack/react-router";

import { useAuthStore } from "@/features/auth/lib/authStore";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    const token = useAuthStore.getState().accessToken;
    if (token === null) {
      throw redirect({ to: "/auth/login" });
    }
    const slug = useOrgStore.getState().currentOrgSlug;
    if (slug !== null && slug.length > 0) {
      throw redirect({ to: "/orgs/$slug", params: { slug } });
    }
    throw redirect({ to: "/orgs" });
  },
});
