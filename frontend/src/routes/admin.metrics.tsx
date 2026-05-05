import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/metrics")({
  component: AdminMetricsPage,
});

function AdminMetricsPage() {
  return (
    <PlaceholderCard
      title="Metrics"
      description="Aggregate platform metrics — orgs, members, audit volume, auth flows."
      issueNumber={20}
    />
  );
}
