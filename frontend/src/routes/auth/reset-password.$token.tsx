import { zodResolver } from "@hookform/resolvers/zod";
import { Link, createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useConsumePasswordResetAuthPasswordResetConsumePost } from "@/api/generated/auth/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthCard } from "@/features/auth/components/AuthCard";
import {
  type PasswordResetCompleteInput,
  passwordResetCompleteSchema,
} from "@/features/auth/lib/schemas";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/auth/reset-password/$token")({
  component: ResetPasswordPage,
});

function ResetPasswordPage() {
  const { token } = Route.useParams();
  const [done, setDone] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PasswordResetCompleteInput>({
    resolver: zodResolver(passwordResetCompleteSchema),
  });

  const consume = useConsumePasswordResetAuthPasswordResetConsumePost();

  const onSubmit = handleSubmit(async ({ password }) => {
    try {
      await consume.mutateAsync({ data: { token, password } });
      setDone(true);
    } catch (e) {
      const code = (e as ApiError | undefined)?.body
        ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
        : undefined;
      const msg =
        code === "auth.token_invalid" || code === "auth.token_expired"
          ? "This reset link is invalid or expired. Request a new one."
          : code === "auth.password_too_short"
            ? "Password too short — use at least 12 characters."
            : "Could not reset the password. Try again.";
      setError("root", { message: msg });
    }
  });

  if (done) {
    return (
      <AuthCard title="Password updated" description="All existing sessions have been signed out.">
        <Button asChild className="w-full">
          <Link to="/auth/login">Sign in with the new password</Link>
        </Button>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Set a new password" description="Enter the password you'd like to use.">
      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-1">
          <Label htmlFor="password">New password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            {...register("password")}
          />
          {errors.password ? (
            <p className="text-sm text-destructive">{errors.password.message}</p>
          ) : (
            <p className="text-xs text-muted-foreground">At least 12 characters.</p>
          )}
        </div>
        {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Saving…" : "Save password"}
        </Button>
      </form>
    </AuthCard>
  );
}
