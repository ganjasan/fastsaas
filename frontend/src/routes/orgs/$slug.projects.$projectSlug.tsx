/**
 * /orgs/$slug/projects/$projectSlug — project detail placeholder. Real content
 * (analyses, scenarios) lands with future epics. The shell exists so the
 * org-switcher path and 404-no-leak route on missing access are testable now.
 */
import { Link, createFileRoute, useParams } from "@tanstack/react-router";
import { useEffect } from "react";

import { useGetProjectOrgsSlugProjectsProjectSlugGet } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export const Route = createFileRoute("/orgs/$slug/projects/$projectSlug")({
  component: ProjectDetailPage,
});

function ProjectDetailPage() {
  const { slug, projectSlug } = useParams({ from: "/orgs/$slug/projects/$projectSlug" });
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);
  useEffect(() => {
    setSlug(slug);
  }, [slug, setSlug]);

  const { data, isLoading, error } = useGetProjectOrgsSlugProjectsProjectSlugGet(slug, projectSlug);

  if (isLoading) return <Skeleton className="m-6 h-64" />;
  if (error || !data) {
    return (
      <main className="mx-auto max-w-4xl p-6">
        <Card>
          <CardHeader>
            <CardTitle>Project not found</CardTitle>
            <CardDescription>It may have been deleted, or you don't have access.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline">
              <Link to="/orgs/$slug/projects" params={{ slug }}>
                Back to projects
              </Link>
            </Button>
          </CardContent>
        </Card>
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
        <p className="text-sm text-muted-foreground">
          {slug} · {data.slug}
        </p>
        {data.description ? (
          <p className="mt-2 text-sm text-foreground">{data.description}</p>
        ) : null}
      </header>
      <Card>
        <CardHeader>
          <CardTitle>Coming soon</CardTitle>
          <CardDescription>
            Analyses, scenarios, and model runs land in a future epic. This shell exists so the
            navigation layer can be exercised now.
          </CardDescription>
        </CardHeader>
      </Card>
    </main>
  );
}
