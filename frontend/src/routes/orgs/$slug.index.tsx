/**
 * /orgs/$slug — Overview page (Render-style).
 *
 * Renders the user's actual data instead of quick-link cards: a Projects
 * subsection lists every project plus a final dashed-bordered tile
 * `+ Create new project` that opens the same dialog used elsewhere.
 *
 * Wrapped by `$slug.tsx` (AppShell layout) which pins the slug into the
 * org store and supplies the Render-style chrome.
 */
import { Link, createFileRoute, useParams } from "@tanstack/react-router";
import { Plus } from "lucide-react";
import { useState } from "react";

import { useListProjectsOrgsSlugProjectsGet } from "@/api/generated/projects/projects";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { CreateProjectDialog } from "@/features/orgs/components/CreateProjectDialog";

export const Route = createFileRoute("/orgs/$slug/")({
  component: OverviewPage,
});

function OverviewPage() {
  const { slug } = useParams({ from: "/orgs/$slug/" });
  const { data: projects, isLoading, refetch } = useListProjectsOrgsSlugProjectsGet(slug);
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Everything happening in this organisation.
        </p>
      </header>

      <section>
        <header className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold tracking-tight">Projects</h2>
        </header>

        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {(projects ?? []).map((p) => (
              <Link
                key={p.id}
                to="/orgs/$slug/projects/$projectSlug"
                params={{ slug, projectSlug: p.slug }}
                className="block"
              >
                <Card className="h-full transition hover:border-primary/40 hover:shadow-sm">
                  <CardHeader>
                    <CardTitle className="text-base">{p.name}</CardTitle>
                    <CardDescription>{p.slug}</CardDescription>
                  </CardHeader>
                </Card>
              </Link>
            ))}

            <CreateProjectDialog
              slug={slug}
              open={createOpen}
              onOpenChange={setCreateOpen}
              onCreated={() => refetch()}
              trigger={
                <button
                  type="button"
                  className="flex h-full min-h-[120px] flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed border-border bg-transparent p-6 text-sm text-muted-foreground transition hover:border-primary/60 hover:text-foreground"
                >
                  <Plus className="h-5 w-5" />
                  <span className="font-medium">Create new project</span>
                </button>
              }
            />
          </div>
        )}
      </section>
    </div>
  );
}
