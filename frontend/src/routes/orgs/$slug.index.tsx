/**
 * /orgs/$slug — overview shell. Pins the slug into the org store on mount
 * (so subsequent API calls carry X-Org). Surfaces tabs/links to projects
 * and member admin.
 */
import { Link, createFileRoute, useParams } from "@tanstack/react-router";
import { useEffect } from "react";

import { useGetOrgOrgsSlugGet } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { OrgSwitcher } from "@/features/orgs/components/OrgSwitcher";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export const Route = createFileRoute("/orgs/$slug/")({
  component: OrgOverviewPage,
});

function OrgOverviewPage() {
  const { slug } = useParams({ from: "/orgs/$slug/" });
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  useEffect(() => {
    setSlug(slug);
  }, [slug, setSlug]);

  const { data, isLoading, error } = useGetOrgOrgsSlugGet(slug);

  return (
    <main className="mx-auto max-w-4xl p-6">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {data?.name ?? <Skeleton className="h-7 w-40" />}
          </h1>
          <p className="text-sm text-muted-foreground">{slug}</p>
        </div>
        <OrgSwitcher />
      </header>

      {error ? (
        <p className="text-sm text-destructive">Could not load organisation.</p>
      ) : isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Projects</CardTitle>
              <CardDescription>Pipelines and analyses live here.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link to="/orgs/$slug/projects" params={{ slug }}>
                  Open projects
                </Link>
              </Button>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Members</CardTitle>
              <CardDescription>Invite people, change roles, remove access.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild variant="outline">
                <Link to="/orgs/$slug/settings/members" params={{ slug }}>
                  Manage members
                </Link>
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </main>
  );
}
