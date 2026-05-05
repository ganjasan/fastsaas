/**
 * /orgs/$slug/settings/members — admins manage who's in the org and pending
 * invitations. Reads gated on `read:organisation`; mutations on `admin`.
 */
import { zodResolver } from "@hookform/resolvers/zod";
import { createFileRoute, useParams } from "@tanstack/react-router";
import { useForm } from "react-hook-form";

import {
  useChangeMemberRoleOrgsSlugMembersActorIdPatch,
  useInviteMemberOrgsSlugMembersInvitePost,
  useListMembersOrgsSlugMembersGet,
  useRemoveMemberOrgsSlugMembersActorIdDelete,
} from "@/api/generated/orgs/orgs";
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
import { type InviteMemberInput, inviteMemberSchema } from "@/features/orgs/lib/schemas";

export const Route = createFileRoute("/orgs/$slug/settings/members")({
  component: MembersPage,
});

const ROLES = ["admin", "member", "viewer", "compliance_officer"] as const;

function MembersPage() {
  const { slug } = useParams({ from: "/orgs/$slug/settings/members" });

  const { data, isLoading, refetch } = useListMembersOrgsSlugMembersGet(slug);
  const invite = useInviteMemberOrgsSlugMembersInvitePost();
  const changeRole = useChangeMemberRoleOrgsSlugMembersActorIdPatch();
  const removeMember = useRemoveMemberOrgsSlugMembersActorIdDelete();

  const {
    register,
    handleSubmit,
    setError,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<InviteMemberInput>({
    resolver: zodResolver(inviteMemberSchema),
    defaultValues: { role: "member" },
  });

  const onInvite = handleSubmit(async (values) => {
    try {
      await invite.mutateAsync({ slug, data: values });
      reset();
      await refetch();
    } catch {
      setError("root", { message: "Could not send invite. Try again." });
    }
  });

  const onChangeRole = async (actorId: string, role: (typeof ROLES)[number]) => {
    await changeRole.mutateAsync({ slug, actorId, data: { role } });
    await refetch();
  };

  const onRemove = async (actorId: string) => {
    if (!window.confirm("Remove this member? They lose access immediately.")) return;
    await removeMember.mutateAsync({ slug, actorId });
    await refetch();
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Members</h2>
        <p className="text-sm text-muted-foreground">Invite people, change roles, remove access.</p>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Invite a member</CardTitle>
          <CardDescription>They'll receive an email with a 7-day invitation link.</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 sm:grid-cols-[2fr_1fr_auto] sm:items-end" onSubmit={onInvite}>
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" autoComplete="off" {...register("email")} />
              {errors.email ? (
                <p className="text-sm text-destructive">{errors.email.message}</p>
              ) : null}
            </div>
            <div className="space-y-1">
              <Label htmlFor="role">Role</Label>
              <Select
                defaultValue="member"
                onValueChange={(v) => setValue("role", v as InviteMemberInput["role"])}
              >
                <SelectTrigger id="role">
                  <SelectValue placeholder="Role" />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? "Sending…" : "Invite"}
            </Button>
            {errors.root ? (
              <p className="col-span-full text-sm text-destructive">{errors.root.message}</p>
            ) : null}
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Members</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <Skeleton className="h-24 w-full" />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.members.map((m) => (
                  <TableRow key={m.actor_id}>
                    <TableCell>{m.display_name}</TableCell>
                    <TableCell>{m.email ?? <em>—</em>}</TableCell>
                    <TableCell>
                      <Select
                        defaultValue={m.role}
                        onValueChange={(v) => onChangeRole(m.actor_id, v as (typeof ROLES)[number])}
                        disabled={m.role === "owner"}
                      >
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {m.role === "owner" ? <SelectItem value="owner">owner</SelectItem> : null}
                          {ROLES.map((r) => (
                            <SelectItem key={r} value={r}>
                              {r}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onRemove(m.actor_id)}
                        disabled={m.role === "owner"}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {data && data.pending.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Pending invitations</CardTitle>
            <CardDescription>
              {data.pending.length} invite{data.pending.length === 1 ? "" : "s"} not yet accepted.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Expires</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.pending.map((p) => (
                  <TableRow key={p.id}>
                    <TableCell>{p.email}</TableCell>
                    <TableCell>{p.role}</TableCell>
                    <TableCell>{new Date(p.expires_at).toLocaleString()}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
