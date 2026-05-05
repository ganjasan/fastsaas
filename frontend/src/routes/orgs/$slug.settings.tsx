/**
 * /orgs/$slug/settings — vertical-tab layout for the org's admin panels.
 * Tabs are URL-driven via TanStack Link; the active tab follows the URL.
 * Children render in the right-hand panel via `<Outlet>`.
 */
import { Link, Outlet, createFileRoute, useLocation, useParams } from "@tanstack/react-router";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

export const Route = createFileRoute("/orgs/$slug/settings")({
  component: SettingsLayout,
});

const TABS = [
  { value: "members", label: "Members" },
  { value: "branding", label: "Branding" },
] as const;

function SettingsLayout() {
  const { slug } = useParams({ from: "/orgs/$slug/settings" });
  const location = useLocation();
  const active = TABS.find((t) => location.pathname.endsWith(`/settings/${t.value}`))?.value;

  return (
    <div className="mx-auto max-w-5xl">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Org admin — members, branding, and other settings.
        </p>
      </header>

      <div className="grid gap-6 md:grid-cols-[12rem_1fr]">
        <Tabs orientation="vertical" value={active}>
          <TabsList className="h-auto w-full flex-col items-stretch gap-1 bg-transparent p-0">
            {TABS.map((tab) => (
              <Link
                key={tab.value}
                to={`/orgs/$slug/settings/${tab.value}` as "/orgs/$slug/settings/members"}
                params={{ slug }}
                className="contents"
              >
                <TabsTrigger
                  value={tab.value}
                  className="w-full justify-start data-[state=active]:bg-accent data-[state=active]:text-accent-foreground"
                >
                  {tab.label}
                </TabsTrigger>
              </Link>
            ))}
          </TabsList>
        </Tabs>
        <div className="min-w-0">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
