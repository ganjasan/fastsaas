import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/design-system")({
  component: AdminDesignSystemPage,
});

function AdminDesignSystemPage() {
  return (
    <PlaceholderCard
      title="Design system"
      description="Phase 2 visual editor: free-form colour pickers, radius slider, font picker, save-as-platform-default / save-as-preset / save-as-org-override."
      issueNumber={23}
    />
  );
}
