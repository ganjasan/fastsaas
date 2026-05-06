/**
 * Org-level dashboard shell — supplies slot content to the generic `<Shell>`
 * primitive. Hosts every `/orgs/{slug}/*` route via `routes/orgs/$slug.tsx`.
 *
 * Routes outside the dashboard surface (`/auth/*`, `/orgs` list, `/orgs/new`,
 * `/orgs/accept-invite/{token}`, `/orgs/accept-share/{token}`) render
 * without this shell.
 */
import { Menu } from "lucide-react";
import type { ReactNode } from "react";

import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { NewMenu } from "@/components/layout/NewMenu";
import { SearchTrigger } from "@/components/layout/SearchTrigger";
import { Shell, useSidebarDrawer } from "@/components/layout/Shell";
import { SidebarBottomChrome } from "@/components/layout/SidebarBottomChrome";
import { ThemeModeToggle } from "@/components/layout/ThemeModeToggle";
import { UserMenu } from "@/components/layout/UserMenu";
import { useDashboardSections } from "@/components/layout/dashboardNav";
import { Button } from "@/components/ui/button";
import { WorkspaceSwitcher } from "@/features/orgs/components/WorkspaceSwitcher";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import "@/features/search"; // side-effect: foundation registrations
import { CommandPalette } from "@/features/search/components/CommandPalette";
import { CommandPaletteHotkey } from "@/features/search/components/CommandPaletteHotkey";

interface AppShellProps {
  children: ReactNode;
}

export function AppShell({ children }: AppShellProps): ReactNode {
  const slug = useOrgStore((s) => s.currentOrgSlug) ?? "";
  const sections = useDashboardSections(slug);

  return (
    <Shell
      sidebarHeader={(collapsed) => <WorkspaceSwitcher collapsed={collapsed} />}
      sidebarSections={sections}
      sidebarBottom={(collapsed) => <SidebarBottomChrome collapsed={collapsed} />}
      topbarLeft={
        <>
          <MobileMenuButton />
          <Breadcrumb />
        </>
      }
      topbarRight={
        <>
          <SearchTrigger />
          <NewMenu />
          <ThemeModeToggle />
          <UserMenu />
        </>
      }
    >
      <CommandPaletteHotkey />
      <CommandPalette workspaceSlug={slug} shell="app" />
      {children}
    </Shell>
  );
}

function MobileMenuButton(): ReactNode {
  const setDrawerOpen = useSidebarDrawer();
  return (
    <Button
      variant="ghost"
      size="icon"
      className="h-8 w-8 lg:hidden"
      aria-label="Open navigation"
      onClick={() => setDrawerOpen(true)}
    >
      <Menu className="h-4 w-4" />
    </Button>
  );
}
