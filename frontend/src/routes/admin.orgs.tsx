import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/orgs")({
  component: AdminOrgsPage,
});

function AdminOrgsPage() {
  return (
    <PlaceholderCard
      title="Orgs"
      description="Every organisation on the platform — drill into members, projects, audit, branding."
      issueNumber={20}
    />
  );
}
