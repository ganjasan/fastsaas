/**
 * `/orgs/$slug` layout route — wraps every nested `$slug.*` route in the
 * AppShell (Sidebar + Topbar). Pinning the slug into the org store happens
 * here once for the whole subtree, instead of in every child.
 */
import { Outlet, createFileRoute, useParams } from "@tanstack/react-router";
import { useEffect } from "react";

import { AppShell } from "@/components/layout/AppShell";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export const Route = createFileRoute("/orgs/$slug")({
  component: OrgLayout,
});

function OrgLayout() {
  const { slug } = useParams({ strict: false }) as { slug: string };
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  useEffect(() => {
    setSlug(slug);
  }, [slug, setSlug]);

  return (
    <AppShell>
      <Outlet />
    </AppShell>
  );
}
