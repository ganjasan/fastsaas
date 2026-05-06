/**
 * /orgs/$slug/projects/$projectSlug — project detail placeholder. Real content
 * (analyses, scenarios) lands with future epics. The shell exists so the
 * org-switcher path and 404-no-leak route on missing access are testable now.
 */
import { Link, createFileRoute, useParams } from "@tanstack/react-router";

import { useGetProjectOrgsSlugProjectsProjectSlugGet } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ProjectSharing } from "@/features/projects/components/ProjectSharing";

export const Route = createFileRoute("/orgs/$slug/projects/$projectSlug")({
  component: ProjectDetailPage,
});

function ProjectDetailPage() {
  const { slug, projectSlug } = useParams({ from: "/orgs/$slug/projects/$projectSlug" });
  const { data, isLoading, error } = useGetProjectOrgsSlugProjectsProjectSlugGet(slug, projectSlug);

  if (isLoading) return <Skeleton className="h-64" />;
  if (error || !data) {
    return (
      <div className="mx-auto max-w-4xl">
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
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">{data.name}</h1>
        <p className="text-sm text-muted-foreground">
          {slug} · {data.slug}
        </p>
        {data.description ? (
          <p className="mt-2 text-sm text-foreground">{data.description}</p>
        ) : null}
      </header>

      <ProjectSharing slug={slug} projectSlug={projectSlug} />

      <Card>
        <CardHeader>
          <CardTitle>Coming soon</CardTitle>
          <CardDescription>
            Analyses, scenarios, and model runs land in a future epic. This shell exists so the
            navigation layer can be exercised now.
          </CardDescription>
        </CardHeader>
      </Card>
    </div>
  );
}
