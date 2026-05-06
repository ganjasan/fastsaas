/**
 * /orgs/accept-share/$token — landing for per-project share emails (UC-001).
 * Posts to /orgs/projects/accept-share, then redirects the guest straight to
 * the project they're now allowed to read.
 */
import { createFileRoute, useNavigate, useParams } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { useAcceptProjectShareOrgsProjectsAcceptSharePost } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuthStore } from "@/features/auth/lib/authStore";
import { setPostAuthRedirect } from "@/features/auth/lib/postAuthRedirect";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/orgs/accept-share/$token")({
  component: AcceptSharePage,
});

function AcceptSharePage() {
  const { token } = useParams({ from: "/orgs/accept-share/$token" });
  const navigate = useNavigate();
  const accessToken = useAuthStore((s) => s.accessToken);
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);
  const accept = useAcceptProjectShareOrgsProjectsAcceptSharePost();

  const [status, setStatus] = useState<"pending" | "ok" | "expired" | "auth" | "error">("pending");
  // Share-accept is a single-use mutation. React Strict Mode (vite dev)
  // remounts effects, which would fire mutateAsync twice — the first call
  // consumes the token, the second sees `share.not_found_or_expired`. Gate
  // with a module-scoped ref keyed on the token so each token is accepted
  // at most once per page lifetime.
  const acceptedRef = useRef<string | null>(null);

  // biome-ignore lint/correctness/useExhaustiveDependencies: single-shot accept; non-listed deps are stable refs
  useEffect(() => {
    if (!accessToken) {
      setStatus("auth");
      return;
    }
    if (acceptedRef.current === token) return;
    acceptedRef.current = token;

    // No cleanup-flag pattern: under React Strict Mode the cleanup runs
    // BEFORE the async work resolves, which would zero out the success
    // handler (the token gets consumed on the network but the UI never
    // navigates). The `acceptedRef` gate above already guarantees the
    // mutation fires exactly once — single-shot is safe to await
    // unconditionally. `navigate()` and the store setters are global, so
    // they still apply after a strict-mode remount.
    void (async () => {
      try {
        const res = await accept.mutateAsync({ data: { token } });
        setSlug(res.org_slug);
        await navigate({
          to: "/orgs/$slug/projects/$projectSlug",
          params: { slug: res.org_slug, projectSlug: res.project_slug },
        });
        setStatus("ok");
      } catch (e) {
        const code = (e as ApiError | undefined)?.body
          ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
          : undefined;
        setStatus(code === "share.not_found_or_expired" ? "expired" : "error");
      }
    })();
  }, [accessToken, token]);

  if (status === "auth") {
    const stashAndGo = (target: "/auth/login" | "/auth/register") => {
      setPostAuthRedirect(`/orgs/accept-share/${token}`);
      void navigate({ to: target });
    };
    return (
      <Frame title="Sign in to view the shared project">
        <p className="text-sm text-muted-foreground">
          You'll come back here automatically after signing in.
        </p>
        <div className="mt-4 flex gap-2">
          <Button onClick={() => stashAndGo("/auth/login")}>Sign in</Button>
          <Button variant="outline" onClick={() => stashAndGo("/auth/register")}>
            Create an account
          </Button>
        </div>
      </Frame>
    );
  }
  if (status === "expired") {
    return (
      <Frame title="Share expired">
        <p className="text-sm text-muted-foreground">
          This share link is no longer valid. Ask the sender for a fresh one.
        </p>
      </Frame>
    );
  }
  if (status === "error") {
    return (
      <Frame title="Could not open the shared project">
        <p className="text-sm text-destructive">Try again, or contact the sender.</p>
      </Frame>
    );
  }
  return <Frame title="Opening the shared project…" />;
}

function Frame({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          <CardDescription>Per-project share</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
    </main>
  );
}
