/**
 * /orgs/$slug/projects — list projects in the pinned org. Members see all,
 * guests see only the projects they hold a `read:project` capability for
 * (server-side filter — the FE just renders the response).
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { Link, createFileRoute, useParams } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import {
  useCreateProjectOrgsSlugProjectsPost,
  useListProjectsOrgsSlugProjectsGet,
} from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { OrgSwitcher } from "@/features/orgs/components/OrgSwitcher";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import { type CreateProjectInput, createProjectSchema } from "@/features/orgs/lib/schemas";
import type { ApiError } from "@/lib/api/client";

export const Route = createFileRoute("/orgs/$slug/projects/")({
  component: ProjectsIndexPage,
});

function ProjectsIndexPage() {
  const { slug } = useParams({ from: "/orgs/$slug/projects/" });
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);
  useEffect(() => {
    setSlug(slug);
  }, [slug, setSlug]);

  const { data, isLoading, refetch } = useListProjectsOrgsSlugProjectsGet(slug);
  const [open, setOpen] = useState(false);

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="text-sm text-muted-foreground">{slug}</p>
        </div>
        <div className="flex items-center gap-2">
          <OrgSwitcher />
          <CreateProjectDialog
            slug={slug}
            open={open}
            onOpenChange={setOpen}
            onCreated={() => refetch()}
          />
        </div>
      </header>

      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : !data || data.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>No projects yet</CardTitle>
            <CardDescription>Create the first project to get started.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button onClick={() => setOpen(true)}>New project</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {data.map((p) => (
            <Card key={p.id} className="transition hover:shadow">
              <CardHeader>
                <CardTitle className="text-lg">
                  <Link
                    to="/orgs/$slug/projects/$projectSlug"
                    params={{ slug, projectSlug: p.slug }}
                    className="hover:underline"
                  >
                    {p.name}
                  </Link>
                </CardTitle>
                <CardDescription>{p.slug}</CardDescription>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}
    </main>
  );
}

function CreateProjectDialog({
  slug,
  open,
  onOpenChange,
  onCreated,
}: {
  slug: string;
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated: () => void;
}) {
  const create = useCreateProjectOrgsSlugProjectsPost();
  const {
    register,
    handleSubmit,
    setError,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<CreateProjectInput>({ resolver: zodResolver(createProjectSchema) });

  const onSubmit = handleSubmit(async (values) => {
    try {
      await create.mutateAsync({ slug, data: values });
      reset();
      onOpenChange(false);
      onCreated();
    } catch (e) {
      const code = (e as ApiError | undefined)?.body
        ? ((e as ApiError).body as { detail?: { code?: string } })?.detail?.code
        : undefined;
      const msg =
        code === "project.slug_invalid"
          ? "Slug must be lowercase letters, digits, hyphens (3–63)."
          : code === "project.slug_reserved"
            ? "That slug is reserved. Pick another."
            : code === "project.slug_taken"
              ? "That slug is already in use here. Pick another."
              : code === "authz.forbidden"
                ? "Only owners and admins can create projects."
                : "Could not create project.";
      setError("root", { message: msg });
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button>New project</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New project</DialogTitle>
          <DialogDescription>Live in {slug}.</DialogDescription>
        </DialogHeader>
        <form className="space-y-3" onSubmit={onSubmit}>
          <div className="space-y-1">
            <Label htmlFor="proj-name">Name</Label>
            <Input id="proj-name" autoComplete="off" {...register("name")} />
            {errors.name ? <p className="text-sm text-destructive">{errors.name.message}</p> : null}
          </div>
          <div className="space-y-1">
            <Label htmlFor="proj-slug">Slug</Label>
            <Input
              id="proj-slug"
              autoComplete="off"
              placeholder="q3-forecast"
              {...register("slug")}
            />
            {errors.slug ? <p className="text-sm text-destructive">{errors.slug.message}</p> : null}
          </div>
          <div className="space-y-1">
            <Label htmlFor="proj-desc">Description (optional)</Label>
            <Textarea id="proj-desc" {...register("description")} />
          </div>
          {errors.root ? <p className="text-sm text-destructive">{errors.root.message}</p> : null}
          <DialogFooter>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
