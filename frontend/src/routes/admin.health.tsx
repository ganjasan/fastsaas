import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/health")({
  component: AdminHealthPage,
});

function AdminHealthPage() {
  return (
    <PlaceholderCard
      title="Health"
      description="Service health probes (Postgres / Redis / Mailhog / OAuth providers), migration state, build version."
      issueNumber={20}
    />
  );
}
