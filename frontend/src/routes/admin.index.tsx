/**
 * `/admin` — Platform-staff Overview page.
 *
 * Welcome landing for platform-staff actors: short blurb + cards summarising
 * what each section does. Real metrics + recent-activity widgets land in #20.
 */
import { Link, createFileRoute } from "@tanstack/react-router";
import {
  FolderOpen,
  Gauge,
  HeartPulse,
  KeyRound,
  type LucideIcon,
  Palette,
  ShieldCheck,
} from "lucide-react";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export const Route = createFileRoute("/admin/")({
  component: AdminOverviewPage,
});

interface SectionSummary {
  to:
    | "/admin/orgs"
    | "/admin/metrics"
    | "/admin/health"
    | "/admin/design-system"
    | "/admin/auth"
    | "/admin/oauth";
  title: string;
  description: string;
  icon: LucideIcon;
}

const SECTIONS: SectionSummary[] = [
  {
    to: "/admin/orgs",
    title: "Orgs",
    description:
      "Every organisation on the platform — drill into members, projects, audit, branding.",
    icon: FolderOpen,
  },
  {
    to: "/admin/metrics",
    title: "Metrics",
    description: "Aggregate platform metrics — orgs, members, audit volume, auth flows.",
    icon: Gauge,
  },
  {
    to: "/admin/health",
    title: "Health",
    description: "Service health probes, migration state, build version.",
    icon: HeartPulse,
  },
  {
    to: "/admin/design-system",
    title: "Design system",
    description: "Phase 2 visual editor — free-form colour pickers, presets, per-org overrides.",
    icon: Palette,
  },
  {
    to: "/admin/auth",
    title: "Auth",
    description: "Auth-page customisation, password policy, registration mode.",
    icon: ShieldCheck,
  },
  {
    to: "/admin/oauth",
    title: "OAuth providers",
    description: "Configure Google / Microsoft / GitHub / generic OIDC at runtime.",
    icon: KeyRound,
  },
];

function AdminOverviewPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Platform admin</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Operator-side controls for the FastSaaS platform. Each section's full content lands in its
          follow-up issue; the foundation here gates access on the platform-staff flag and surfaces
          the navigation tree.
        </p>
      </header>

      <section>
        <header className="mb-4">
          <h2 className="text-lg font-semibold tracking-tight">Sections</h2>
        </header>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {SECTIONS.map((s) => (
            <Link key={s.to} to={s.to} className="block">
              <Card className="h-full transition hover:border-primary/40 hover:shadow-sm">
                <CardHeader>
                  <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-md bg-primary/10 text-primary">
                    <s.icon className="h-4 w-4" />
                  </div>
                  <CardTitle className="text-base">{s.title}</CardTitle>
                  <CardDescription className="text-sm">{s.description}</CardDescription>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
