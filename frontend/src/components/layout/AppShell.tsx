/**
 * Dashboard shell — Sidebar (left, collapsible) + Topbar + main content
 * outlet. Hosts every `/orgs/{slug}/*` route via the `$slug.tsx` layout
 * route (see `routes/orgs/$slug.tsx`). Routes outside the dashboard
 * (login, /orgs/new, /orgs list) render without the shell.
 */
import type { ReactNode } from "react";

import { Sidebar } from "@/components/layout/Sidebar";
import { Topbar } from "@/components/layout/Topbar";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps): ReactNode {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
