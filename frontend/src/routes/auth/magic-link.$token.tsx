import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import {
  useConsumeMagicLinkAuthMagicLinkConsumePost,
  useMeAuthMeGet,
} from "@/api/generated/auth/auth";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { useAuthStore } from "@/features/auth/lib/authStore";

type Status = "pending" | "ok" | "error";

export const Route = createFileRoute("/auth/magic-link/$token")({
  component: MagicLinkPage,
});

function MagicLinkPage() {
  const { token } = Route.useParams();
  const [status, setStatus] = useState<Status>("pending");
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const setCurrentActor = useAuthStore((s) => s.setCurrentActor);
  const consume = useConsumeMagicLinkAuthMagicLinkConsumePost();
  const meQuery = useMeAuthMeGet({ query: { enabled: false } });
  const mutate = consume.mutateAsync;
  const refetchMe = meQuery.refetch;
  // StrictMode runs effects twice; the consume call is single-use, so guard
  // against the second invocation flipping the UI into the "consumed" error.
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;
    void (async () => {
      try {
        const tokens = await mutate({ data: { token } });
        setAccessToken(tokens.access_token);
        const me = await refetchMe();
        if (me.data) setCurrentActor(me.data);
        setStatus("ok");
        await navigate({ to: "/" });
      } catch {
        setStatus("error");
      }
    })();
  }, [mutate, refetchMe, navigate, setAccessToken, setCurrentActor, token]);

  if (status === "error") {
    return (
      <AuthCard title="Link invalid or expired" description="Sign-in link can no longer be used.">
        <Button asChild variant="outline" className="w-full">
          <Link to="/auth/login">Back to sign in</Link>
        </Button>
      </AuthCard>
    );
  }
  return <AuthCard title="Signing you in…" />;
}
