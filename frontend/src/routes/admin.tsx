/**
 * `/admin` parent layout — gates the staff-only surface.
 *
 * Auth check runs in `beforeLoad` (async, synchronous from the user's
 * point of view: redirects fire before the layout component renders, so
 * non-staff never see a blank flash).
 *
 * Behaviour:
 * - 401 (no token) → redirect to `/auth/login`.
 * - 403 (not staff) → redirect to `/orgs`.
 * - 200 → render the AdminShell with the matched child route.
 * - 5xx / network error → fall through; the route's error boundary handles it.
 */
import { Outlet, createFileRoute, redirect } from "@tanstack/react-router";

import { adminMeAdminMeGet } from "@/api/generated/admin/admin";
import { AdminShell } from "@/components/layout/AdminShell";

export const Route = createFileRoute("/admin")({
  beforeLoad: async () => {
    try {
      await adminMeAdminMeGet();
    } catch (e) {
      const status = (e as { status?: number }).status;
      if (status === 401) {
        throw redirect({ to: "/auth/login" });
      }
      if (status === 403) {
        throw redirect({ to: "/orgs" });
      }
      // Other errors propagate to the router's error boundary.
      throw e;
    }
  },
  component: AdminLayout,
});

function AdminLayout() {
  return (
    <AdminShell>
      <Outlet />
    </AdminShell>
  );
}
