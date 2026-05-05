/**
 * /orgs/$slug/projects — list projects in the pinned org. Members see all,
 * guests see only the projects they hold a `read:project` capability for
 * (server-side filter — the FE just renders the response).
 */
import { Link, createFileRoute, useParams, useSearch } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { useListProjectsOrgsSlugProjectsGet } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateProjectDialog } from "@/features/orgs/components/CreateProjectDialog";

interface ProjectsSearch {
  /** When `?new=1` the create dialog opens on mount (driven by the
   * topbar `+ New ⌄ → Create project` action). */
  new?: string;
}

export const Route = createFileRoute("/orgs/$slug/projects/")({
  component: ProjectsIndexPage,
  validateSearch: (raw): ProjectsSearch => ({
    new: typeof raw.new === "string" ? raw.new : undefined,
  }),
});

function ProjectsIndexPage() {
  const { slug } = useParams({ from: "/orgs/$slug/projects/" });
  const search = useSearch({ from: "/orgs/$slug/projects/" });
  const { data, isLoading, refetch } = useListProjectsOrgsSlugProjectsGet(slug);
  const [open, setOpen] = useState(false);

  // Open the create dialog when arriving via `?new=1` from the topbar.
  useEffect(() => {
    if (search.new === "1") setOpen(true);
  }, [search.new]);

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">{slug}</p>
        </div>
        <CreateProjectDialog
          slug={slug}
          open={open}
          onOpenChange={setOpen}
          onCreated={() => refetch()}
          trigger={<Button>New project</Button>}
        />
      </header>

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : !data || data.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No projects yet</CardTitle>
            <CardDescription>Create the first project to get started.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.map((p) => (
            <Card key={p.id} className="transition hover:shadow">
              <CardHeader>
                <CardTitle className="text-lg">
                  <Link
                    to="/orgs/$slug/projects/$projectSlug"
                    params={{ slug, projectSlug: p.slug }}
                    className="hover:underline"
                  >
                    {p.name}
                  </Link>
                </CardTitle>
                <CardDescription>{p.slug}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
