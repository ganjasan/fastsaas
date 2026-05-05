/**
 * Project-create dialog used by both `/orgs/{slug}/projects` (the Projects
 * list page) and `/orgs/{slug}` (Overview's dashed `+ Create new project`
 * tile). Identical contract — validation, error mapping, success callback.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import type { ReactNode } from "react";
import { useForm } from "react-hook-form";

import { useCreateProjectOrgsSlugProjectsPost } from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
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
import { Textarea } from "@/components/ui/textarea";
import { type CreateProjectInput, createProjectSchema } from "@/features/orgs/lib/schemas";
import type { ApiError } from "@/lib/api/client";

interface CreateProjectDialogProps {
  slug: string;
  open: boolean;
  onOpenChange: (next: boolean) => void;
  onCreated: () => void;
  /** Custom trigger element (button / dashed tile / etc.). When omitted,
   * the dialog is treated as fully controlled (caller toggles `open`). */
  trigger?: ReactNode;
}

export function CreateProjectDialog({
  slug,
  open,
  onOpenChange,
  onCreated,
  trigger,
}: CreateProjectDialogProps) {
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
      {trigger ? <DialogTrigger asChild>{trigger}</DialogTrigger> : null}
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
