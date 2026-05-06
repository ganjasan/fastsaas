/**
 * `/orgs/$slug/projects/$projectSlug/sharing` — Project Sharing tab.
 *
 * Owner / admin issues guest invite links here. The bulk of the
 * implementation lives in `<ProjectSharing>` (per UC-001 + issue #30).
 */
import { createFileRoute, useParams } from "@tanstack/react-router";

import { ProjectSharing } from "@/features/projects/components/ProjectSharing";

export const Route = createFileRoute("/orgs/$slug/projects/$projectSlug/sharing")({
  component: ProjectSharingPage,
});

function ProjectSharingPage() {
  const { slug, projectSlug } = useParams({
    from: "/orgs/$slug/projects/$projectSlug/sharing",
  });
  return <ProjectSharing slug={slug} projectSlug={projectSlug} />;
}
