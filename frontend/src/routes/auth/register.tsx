import { zodResolver } from "@hookform/resolvers/zod";
import { Link, createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useForm } from "react-hook-form";

import { useRegisterAuthRegisterPost } from "@/api/generated/auth/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { type RegisterInput, registerSchema } from "@/features/auth/lib/schemas";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/auth/register")({
  component: RegisterPage,
});

function RegisterPage() {
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterInput>({ resolver: zodResolver(registerSchema) });

  const reg = useRegisterAuthRegisterPost();

  const onSubmit = handleSubmit(async (values) => {
    try {
      await reg.mutateAsync({ data: values });
      setSubmittedEmail(values.email);
    } catch (e) {
      const code = (e as ApiError | undefined)?.body
        ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
        : undefined;
      const msg =
        code === "auth.email_taken"
          ? "An account with that email already exists."
          : code === "auth.password_too_short"
            ? "Password too short — use at least 12 characters."
            : "Could not create the account. Try again.";
      setError("root", { message: msg });
    }
  });

  if (submittedEmail) {
    return (
      <AuthCard
        title="Check your inbox"
        description={`We sent a verification link to ${submittedEmail}. Click it to activate your account.`}
      >
        <p className="text-sm text-muted-foreground">
          The link is valid for 24 hours. You can close this tab.
        </p>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Create your account" description="Start with email + password.">
      <form className="space-y-4" onSubmit={onSubmit}>
        <div className="space-y-1">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" {...register("email")} />
          {errors.email ? <p className="text-sm text-destructive">{errors.email.message}</p> : null}
        </div>
        <div className="space-y-1">
          <Label htmlFor="password">Password</Label>
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
          {isSubmitting ? "Creating…" : "Create account"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link to="/auth/login" className="underline">
          Sign in
        </Link>
      </p>
    </AuthCard>
  );
}
