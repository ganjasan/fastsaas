import { createFileRoute } from "@tanstack/react-router";

import { PlaceholderCard } from "@/features/admin/PlaceholderCard";

export const Route = createFileRoute("/admin/auth")({
  component: AdminAuthPage,
});

function AdminAuthPage() {
  return (
    <PlaceholderCard
      title="Auth"
      description="Auth-page customisation (logo, primary colour, hero copy), password policy, registration mode (open / invite-only / domain-allowlist)."
      issueNumber={21}
    />
  );
}
