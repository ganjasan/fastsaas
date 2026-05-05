import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/oauth")({
  component: AdminOAuthPage,
});

function AdminOAuthPage() {
  return (
    <PlaceholderCard
      title="OAuth providers"
      description="Configure Google / Microsoft / GitHub / generic OIDC providers at runtime — add, edit, rotate secrets, test-connection."
      issueNumber={22}
    />
  );
}
