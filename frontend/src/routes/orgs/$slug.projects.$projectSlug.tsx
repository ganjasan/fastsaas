/**
 * `/orgs/$slug/projects/$projectSlug` — project detail layout.
 *
 * Parent layout for project subroutes (Overview, Sharing). Renders the
 * project header + an Outlet for the matched child page. The active
 * project's data is fetched here once and exposed via context for child
 * routes to consume without refetching.
 *
 * The 404-no-leak path (project soft-deleted or actor lacks access)
 * lives here so every subroute inherits it for free.
 */
import { Link, Outlet, createFileRoute, useParams } from "@tanstack/react-router";
import { createContext, useContext } from "react";

import type { ProjectRead } from "@/api/generated/fastSaaS.schemas";
import { useGetProjectOrgsSlugProjectsProjectSlugGet } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const Route = createFileRoute("/orgs/$slug/projects/$projectSlug")({
  component: ProjectLayout,
});

interface ProjectContextValue {
  slug: string;
  projectSlug: string;
  project: ProjectRead;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (ctx === null) {
    throw new Error("useProjectContext must be used inside the project layout");
  }
  return ctx;
}

function ProjectLayout() {
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
    <ProjectContext.Provider value={{ slug, projectSlug, project: data }}>
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
        <Outlet />
      </div>
    </ProjectContext.Provider>
  );
}
