/**
 * /orgs/new — create-an-organisation form. Slug regex matches the backend's
 * `org_slug_format` CHECK; reserved-list is server-side only.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";

import { useCreateOrgOrgsPost } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import { type CreateOrgInput, createOrgSchema } from "@/features/orgs/lib/schemas";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/orgs/new")({
  component: NewOrgPage,
});

function NewOrgPage() {
  const navigate = useNavigate();
  const setCurrentOrgSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<CreateOrgInput>({ resolver: zodResolver(createOrgSchema) });
  const createOrg = useCreateOrgOrgsPost();

  const onSubmit = handleSubmit(async (values) => {
    try {
      const org = await createOrg.mutateAsync({ data: values });
      setCurrentOrgSlug(org.slug);
      await navigate({ to: "/orgs/$slug", params: { slug: org.slug } });
    } catch (e) {
      const code = (e as ApiError | undefined)?.body
        ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
        : undefined;
      const msg =
        code === "org.slug_invalid"
          ? "Slug must be lowercase letters, digits, or hyphens (3–63 chars)."
          : code === "org.slug_reserved"
            ? "That slug is reserved. Pick another."
            : code === "org.slug_taken"
              ? "That slug is already in use. Pick another."
              : "Could not create organisation. Try again.";
      setError("root", { message: msg });
    }
  });

  return (
    <main className="mx-auto max-w-md p-6">
      <Card>
        <CardHeader>
          <CardTitle>New organisation</CardTitle>
          <CardDescription>You'll be its owner. Members and projects come later.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={onSubmit}>
            <div className="space-y-1">
              <Label htmlFor="name">Name</Label>
              <Input id="name" autoComplete="off" {...register("name")} />
              {errors.name ? (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              ) : null}
            </div>
            <div className="space-y-1">
              <Label htmlFor="slug">Slug</Label>
              <Input id="slug" autoComplete="off" placeholder="acme-co" {...register("slug")} />
              <p className="text-xs text-muted-foreground">
                Used in URLs. Lowercase letters, digits, hyphens only.
              </p>
              {errors.slug ? (
                <p className="text-sm text-destructive">{errors.slug.message}</p>
              ) : null}
            </div>
            {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
            <Button type="submit" className="w-full" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create organisation"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
