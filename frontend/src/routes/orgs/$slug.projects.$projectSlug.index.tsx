/**
 * `/orgs/$slug/projects/$projectSlug/` — Project Overview tab.
 *
 * Placeholder for analyses / scenarios / model runs (future epics). The
 * project header, fetch, and 404-no-leak path live in the parent layout
 * (`$slug.projects.$projectSlug.tsx`); this file is just the body for
 * the Overview sidebar tab.
 */
import { createFileRoute } from "@tanstack/react-router";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const Route = createFileRoute("/orgs/$slug/projects/$projectSlug/")({
  component: ProjectOverviewPage,
});

function ProjectOverviewPage() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Coming soon</CardTitle>
        <CardDescription>
          Analyses, scenarios, and model runs land in a future epic. This shell exists so the
          navigation layer can be exercised now.
        </CardDescription>
      </CardHeader>
    </Card>
  );
}
