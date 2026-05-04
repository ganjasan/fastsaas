/**
 * /orgs — list the caller's orgs. First-login users get the empty-state
 * CTA pointing at /orgs/new.
 */
import { Link, createFileRoute } from "@tanstack/react-router";

import { useListMyOrgsOrgsGet } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export const Route = createFileRoute("/orgs/")({
  component: OrgsIndexPage,
});

function OrgsIndexPage() {
  const { data, isLoading, error } = useListMyOrgsOrgsGet();
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  if (isLoading) {
    return (
      <PageShell title="Your organisations">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-12 w-full" />
      </PageShell>
    );
  }
  if (error) {
    return (
      <PageShell title="Your organisations">
        <p className="text-sm text-destructive">Could not load organisations.</p>
      </PageShell>
    );
  }
  if (!data || data.length === 0) {
    return (
      <PageShell title="Welcome to FastSaaS">
        <Card>
          <CardHeader>
            <CardTitle>Create your first organisation</CardTitle>
            <CardDescription>
              An organisation groups projects, members, and settings. You'll become its owner.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/orgs/new">Create organisation</Link>
            </Button>
          </CardContent>
        </Card>
      </PageShell>
    );
  }

  return (
    <PageShell title="Your organisations">
      <div className="space-y-3">
        {data.map((o) => (
          <Card key={o.slug} className="transition hover:shadow">
            <CardHeader>
              <div className="flex items-center justify-between gap-2">
                <CardTitle className="text-lg">
                  <Link
                    to="/orgs/$slug"
                    params={{ slug: o.slug }}
                    onClick={() => setSlug(o.slug)}
                    className="hover:underline"
                  >
                    {o.name}
                  </Link>
                </CardTitle>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                  {o.role}
                </span>
              </div>
              <CardDescription>{o.slug}</CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>
      <div className="mt-6">
        <Button asChild variant="outline">
          <Link to="/orgs/new">Create new organisation</Link>
        </Button>
      </div>
    </PageShell>
  );
}

function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <main className="mx-auto max-w-3xl p-6">
      <h1 className="mb-6 text-2xl font-semibold tracking-tight">{title}</h1>
      {children}
    </main>
  );
}
