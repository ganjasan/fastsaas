import { Link, createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";

import { useVerifyEmailAuthVerifyEmailPost } from "@/api/generated/auth/auth";
import { Button } from "@/components/ui/button";
import { AuthCard } from "@/features/auth/components/AuthCard";

type Status = "pending" | "ok" | "error";

export const Route = createFileRoute("/auth/verify-email/$token")({
  component: VerifyEmailPage,
});

function VerifyEmailPage() {
  const { token } = Route.useParams();
  const [status, setStatus] = useState<Status>("pending");
  const verify = useVerifyEmailAuthVerifyEmailPost();
  const mutate = verify.mutateAsync;
  // StrictMode runs effects twice; the consume call is single-use, so guard
  // against the second invocation flipping the UI into the "consumed" error.
  const calledRef = useRef(false);

  useEffect(() => {
    if (calledRef.current) return;
    calledRef.current = true;
    void (async () => {
      try {
        await mutate({ data: { token } });
        setStatus("ok");
      } catch {
        setStatus("error");
      }
    })();
  }, [mutate, token]);

  if (status === "pending") {
    return <AuthCard title="Verifying…" description="One moment while we activate your account." />;
  }
  if (status === "ok") {
    return (
      <AuthCard title="Email verified" description="Your account is active. You can sign in now.">
        <Button asChild className="w-full">
          <Link to="/auth/login">Continue to sign in</Link>
        </Button>
      </AuthCard>
    );
  }
  return (
    <AuthCard
      title="Link invalid or expired"
      description="This verification link can no longer be used."
    >
      <Button asChild variant="outline" className="w-full">
        <Link to="/auth/register">Register again</Link>
      </Button>
    </AuthCard>
  );
}
