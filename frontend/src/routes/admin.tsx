/**
 * `/admin` parent layout — gates the staff-only surface.
 *
 * Calls `useAdminMe` (`GET /admin/me`) at mount. The dependency layer on the
 * backend rejects unauthenticated calls with 401 and non-staff with 403:
 * - 401 → redirect to `/auth/login` (so the user can come back and try)
 * - 403 → redirect to `/orgs` (their normal landing — they are authenticated
 *         but not staff; the admin shell isn't for them)
 * - 200 → render the AdminShell with the matched child route in the outlet.
 *
 * `useAdminMe` is the orval-generated hook that maps to GET /admin/me.
 */
import { Outlet, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";

import { useAdminMeAdminMeGet } from "@/api/generated/admin/admin";
import { AdminShell } from "@/components/layout/AdminShell";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/admin")({
  component: AdminLayout,
});

function AdminLayout() {
  const navigate = useNavigate();
  const { data, isLoading, error } = useAdminMeAdminMeGet({
    query: { retry: false },
  });

  useEffect(() => {
    if (error === null || error === undefined) return;
    const status = (error as { status?: number }).status;
    if (status === 401) {
      void navigate({ to: "/auth/login" });
    } else if (status === 403) {
      void navigate({ to: "/orgs" });
    }
    // Other errors (5xx, network) fall through to the error UI below.
  }, [error, navigate]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Skeleton className="h-32 w-96" />
      </div>
    );
  }
  if (error || !data) {
    // The redirect above runs in useEffect; on first render we still pass
    // through this branch. Render an empty placeholder so we don't flash
    // the AdminShell to a non-staff user while the navigate() resolves.
    return null;
  }

  return (
    <AdminShell>
      <Outlet />
    </AdminShell>
  );
}
