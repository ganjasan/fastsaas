import { zodResolver } from "@hookform/resolvers/zod";
import { Link, createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";

import { useLoginAuthLoginPost, useMeAuthMeGet } from "@/api/generated/auth/auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { AuthCard } from "@/features/auth/components/AuthCard";
import { useAuthStore } from "@/features/auth/lib/authStore";
import { type LoginInput, loginSchema } from "@/features/auth/lib/schemas";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/auth/login")({
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const setAccessToken = useAuthStore((s) => s.setAccessToken);
  const setCurrentActor = useAuthStore((s) => s.setCurrentActor);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginInput>({ resolver: zodResolver(loginSchema) });

  const login = useLoginAuthLoginPost();
  const meQuery = useMeAuthMeGet({ query: { enabled: false } });

  const onSubmit = handleSubmit(async (values) => {
    try {
      const tokens = await login.mutateAsync({ data: values });
      setAccessToken(tokens.access_token);
      const actor = await meQuery.refetch();
      if (actor.data) setCurrentActor(actor.data);
      await navigate({ to: "/" });
    } catch (e) {
      const code = (e as ApiError | undefined)?.body
        ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
        : undefined;
      const msg =
        code === "auth.email_unverified"
          ? "Verify your email before signing in."
          : code === "auth.invalid_credentials"
            ? "Invalid email or password."
            : "Sign-in failed. Try again.";
      setError("root", { message: msg });
    }
  });

  return (
    <AuthCard title="Sign in" description="Welcome back to FastSaaS.">
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
            autoComplete="current-password"
            {...register("password")}
          />
          {errors.password ? (
            <p className="text-sm text-destructive">{errors.password.message}</p>
          ) : null}
        </div>
        {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
        <Button type="submit" className="w-full" disabled={isSubmitting}>
          {isSubmitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>
      <p className="mt-4 text-center text-sm text-muted-foreground">
        New here?{" "}
        <Link to="/auth/register" className="underline">
          Create an account
        </Link>
      </p>
    </AuthCard>
  );
}
