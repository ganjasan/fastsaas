/**
 * /orgs/accept-invite/$token — landing page for the invitation email link.
 * Posts the token to the backend; redirects to the joined org on success.
 */
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";

import { useAcceptInviteOrgsMembersAcceptPost } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/features/auth/lib/authStore";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/orgs/accept-invite/$token")({
  component: AcceptInvitePage,
});

function AcceptInvitePage() {
  const { token } = useParams({ from: "/orgs/accept-invite/$token" });
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);
  const accept = useAcceptInviteOrgsMembersAcceptPost();

  const [status, setStatus] = useState<"pending" | "ok" | "expired" | "auth" | "error">("pending");

  // biome-ignore lint/correctness/useExhaustiveDependencies: single-shot accept; non-listed deps are stable refs
  useEffect(() => {
    if (!accessToken) {
      setStatus("auth");
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await accept.mutateAsync({ data: { token } });
        if (cancelled) return;
        setSlug(res.org_slug);
        await navigate({ to: "/orgs/$slug", params: { slug: res.org_slug } });
        setStatus("ok");
      } catch (e) {
        if (cancelled) return;
        const code = (e as ApiError | undefined)?.body
          ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
          : undefined;
        setStatus(code === "invite.not_found_or_expired" ? "expired" : "error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [accessToken, token]);

  if (status === "auth") {
    return (
      <Frame title="Sign in to accept">
        <p className="text-sm text-muted-foreground">
          You need a FastSaaS account before joining the organisation. The invite will still work
          after you sign in.
        </p>
        <Button className="mt-4" onClick={() => navigate({ to: "/auth/login" })}>
          Go to sign-in
        </Button>
      </Frame>
    );
  }
  if (status === "expired") {
    return (
      <Frame title="Invitation expired">
        <p className="text-sm text-muted-foreground">
          This invite is no longer valid. Ask the inviter to send a fresh one.
        </p>
      </Frame>
    );
  }
  if (status === "error") {
    return (
      <Frame title="Could not accept invite">
        <p className="text-sm text-destructive">Try again, or contact the inviter.</p>
      </Frame>
    );
  }
  return <Frame title="Accepting invitation…" />;
}

function Frame({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>Organisation invitation</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}
