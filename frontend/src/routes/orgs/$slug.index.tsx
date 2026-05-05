/**
 * /orgs/$slug — overview page. Wrapped by `$slug.tsx` (AppShell layout),
 * which also handles pinning the slug into the org store, so this page
 * focuses on its own content.
 */
import { Link, createFileRoute, useParams } from "@tanstack/react-router";

import { useGetOrgOrgsSlugGet } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/orgs/$slug/")({
  component: OrgOverviewPage,
});

function OrgOverviewPage() {
  const { slug } = useParams({ from: "/orgs/$slug/" });
  const { data, isLoading, error } = useGetOrgOrgsSlugGet(slug);

  return (
    <div className="mx-auto max-w-4xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">
          {data?.name ?? <Skeleton className="h-7 w-40" />}
        </h1>
        <p className="text-sm text-muted-foreground">{slug}</p>
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
    </div>
  );
}
