/**
 * Project sharing surface — owner/admin issues guest access (UC-001).
 *
 * Backend already implements the per-project guest pattern:
 * - `POST /orgs/{slug}/projects/{slug}/shares` mints a one-time token,
 *   emails it to the recipient, returns `(id, email, expires_at, raw_token)`.
 * - `GET /orgs/{slug}/projects/{slug}/shares` lists pending shares.
 * - `DELETE /orgs/{slug}/projects/{slug}/shares/{id}` revokes.
 *
 * The recipient flow is covered by `routes/orgs/accept-share.$token.tsx`.
 * This component is the missing owner-side surface — without it, operators
 * had to curl the API.
 *
 * The raw_token is shown ONCE right after creation in a copyable input.
 * The backend stores `sha256(token)` so re-display is impossible after
 * navigation away — same UX as the org-invitation pattern.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";

import type { ProjectShareResponse } from "@/api/generated/fastSaaS.schemas";
import {
  getListProjectSharesOrgsSlugProjectsProjectSlugSharesGetQueryKey,
  listProjectSharesOrgsSlugProjectsProjectSlugSharesGet,
  revokeProjectShareOrgsSlugProjectsProjectSlugSharesShareIdDelete,
  shareProjectOrgsSlugProjectsProjectSlugSharesPost,
} from "@/api/generated/projects/projects";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { type ShareProjectInput, shareProjectSchema } from "@/features/orgs/lib/schemas";

interface ProjectSharingProps {
  slug: string;
  projectSlug: string;
}

const TTL_OPTIONS = [3, 7, 14, 30] as const;

export function ProjectSharing({ slug, projectSlug }: ProjectSharingProps) {
  const queryClient = useQueryClient();
  const [lastIssued, setLastIssued] = useState<ProjectShareResponse | null>(null);

  const sharesKey = getListProjectSharesOrgsSlugProjectsProjectSlugSharesGetQueryKey(
    slug,
    projectSlug,
  );
  const sharesQuery = useQuery({
    queryKey: sharesKey,
    queryFn: () => listProjectSharesOrgsSlugProjectsProjectSlugSharesGet(slug, projectSlug),
  });

  const create = useMutation({
    mutationFn: (input: ShareProjectInput) =>
      shareProjectOrgsSlugProjectsProjectSlugSharesPost(slug, projectSlug, input),
    onSuccess: async (response) => {
      setLastIssued(response);
      await queryClient.invalidateQueries({ queryKey: sharesKey });
    },
  });

  const revoke = useMutation({
    mutationFn: (shareId: string) =>
      revokeProjectShareOrgsSlugProjectsProjectSlugSharesShareIdDelete(slug, projectSlug, shareId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: sharesKey });
    },
  });

  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ShareProjectInput>({
    resolver: zodResolver(shareProjectSchema),
    defaultValues: { ttl_days: 14 },
  });

  const onSubmit = handleSubmit(async (values) => {
    await create.mutateAsync(values);
    reset({ ttl_days: 14 });
  });

  const onRevoke = async (shareId: string, email: string) => {
    if (!window.confirm(`Revoke invite for ${email}?`)) return;
    await revoke.mutateAsync(shareId);
  };

  return (
    <section className="space-y-4">
      <header>
        <h2 className="text-lg font-semibold tracking-tight">Sharing</h2>
        <p className="text-sm text-muted-foreground">
          Issue a one-time read-only invite link. Anyone who opens the link gets read access — the
          email field is just where we deliver it. Guests see only this project, never your org's
          other work.
        </p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Invite a guest</CardTitle>
          <CardDescription>
            We'll email this address an invite link. Anyone who opens the link gets read access to
            this project — the link is single-use, so don't forward it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-[2fr_8rem_auto] sm:items-end"
            onSubmit={onSubmit}
          >
            <div className="space-y-1">
              <Label htmlFor="share-email">Email</Label>
              <Input id="share-email" type="email" autoComplete="off" {...register("email")} />
              {errors.email ? (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              ) : null}
            </div>
            <div className="space-y-1">
              <Label htmlFor="share-ttl">Expires in</Label>
              <Select
                defaultValue="14"
                onValueChange={(v) => setValue("ttl_days", Number.parseInt(v, 10))}
              >
                <SelectTrigger id="share-ttl">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TTL_OPTIONS.map((days) => (
                    <SelectItem key={days} value={String(days)}>
                      {days} days
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Sending…" : "Share"}
            </Button>
            {create.isError ? (
              <p className="col-span-full text-sm text-destructive">
                Could not issue invite. Try again.
              </p>
            ) : null}
          </form>

          {lastIssued && (
            <IssuedShareReveal share={lastIssued} onClose={() => setLastIssued(null)} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Pending invites</CardTitle>
          <CardDescription>
            Issued, not yet accepted. Revoke to invalidate the invite link.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {sharesQuery.isLoading ? (
            <Skeleton className="h-16 w-full" />
          ) : !sharesQuery.data || sharesQuery.data.length === 0 ? (
            <p className="text-sm text-muted-foreground">No pending invites.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sharesQuery.data.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell>{s.email}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(s.expires_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onRevoke(s.id, s.email)}
                        disabled={revoke.isPending}
                      >
                        Revoke
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

function IssuedShareReveal({
  share,
  onClose,
}: {
  share: ProjectShareResponse;
  onClose: () => void;
}) {
  const link = `${window.location.origin}/orgs/accept-share/${share.raw_token}`;
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard may be unavailable; fall back to a manual select.
    }
  };

  return (
    <div className="mt-4 rounded-md border border-primary/40 bg-primary/5 p-3">
      <p className="text-sm font-medium">Invite link for {share.email}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Copy this once — it disappears when you navigate away. The same link is also in the email we
        just sent.
      </p>
      <div className="mt-2 flex items-center gap-2">
        <Input readOnly value={link} className="font-mono text-xs" />
        <Button variant="outline" size="sm" onClick={onCopy} className="shrink-0">
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          <span className="ml-1.5">{copied ? "Copied" : "Copy"}</span>
        </Button>
        <Button variant="ghost" size="sm" onClick={onClose}>
          Dismiss
        </Button>
      </div>
    </div>
  );
}
