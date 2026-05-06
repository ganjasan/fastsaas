/**
 * Platform-staff admin shell — supplies slot content to the generic `<Shell>`
 * primitive (#24). Hosts every `/admin/*` route via `routes/admin.tsx`.
 *
 * Visually distinct from the org dashboard: the sidebar header carries a
 * "PLATFORM ADMIN" pill (no workspace switcher — admin is cross-org), nav
 * is grouped under UPPERCASE labels (OPERATIONS / CONFIGURATION), and the
 * topbar drops the workspace controls (no `+ New ⌄`, no theme toggle, no
 * org-switcher) — only Search + user menu.
 *
 * The neutral-theme requirement from design.md D6 is best-effort here:
 * the org `<ThemeProvider>` still wraps the page, but the AdminShell's
 * inner content reads with a stable default-preset when the staff member
 * also belongs to a themed org. Full theme override is a follow-up.
 */
import { FolderOpen, Gauge, HeartPulse, KeyRound, Palette, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";

import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { SearchTrigger } from "@/components/layout/SearchTrigger";
import { type NavSection, Shell } from "@/components/layout/Shell";
import { SidebarBottomChrome } from "@/components/layout/SidebarBottomChrome";
import { UserMenu } from "@/components/layout/UserMenu";
import "@/features/search"; // side-effect: foundation registrations
import { CommandPalette } from "@/features/search/components/CommandPalette";
import { CommandPaletteHotkey } from "@/features/search/components/CommandPaletteHotkey";

interface AdminShellProps {
  children: ReactNode;
}

const NAV_SECTIONS: NavSection[] = [
  {
    label: "OPERATIONS",
    items: [
      { to: "/admin/orgs", label: "Orgs", icon: FolderOpen },
      { to: "/admin/metrics", label: "Metrics", icon: Gauge },
      { to: "/admin/health", label: "Health", icon: HeartPulse },
    ],
  },
  {
    label: "CONFIGURATION",
    items: [
      { to: "/admin/design-system", label: "Design system", icon: Palette },
      { to: "/admin/auth", label: "Auth", icon: ShieldCheck },
      { to: "/admin/oauth", label: "OAuth providers", icon: KeyRound },
    ],
  },
];

export function AdminShell({ children }: AdminShellProps): ReactNode {
  return (
    <Shell
      sidebarHeader={(collapsed) => <PlatformAdminPill collapsed={collapsed} />}
      sidebarSections={NAV_SECTIONS}
      sidebarBottom={(collapsed) => <SidebarBottomChrome collapsed={collapsed} />}
      topbarLeft={<Breadcrumb />}
      topbarRight={
        <>
          <SearchTrigger />
          <UserMenu />
        </>
      }
    >
      <CommandPaletteHotkey />
      <CommandPalette workspaceSlug="" shell="admin" />
      {children}
    </Shell>
  );
}

function PlatformAdminPill({ collapsed }: { collapsed: boolean }): ReactNode {
  if (collapsed) {
    return (
      <div className="flex w-full items-center justify-center">
        <span
          aria-hidden="true"
          className="flex h-8 w-8 items-center justify-center rounded-md bg-destructive/10 text-xs font-bold text-destructive"
        >
          P
        </span>
      </div>
    );
  }
  return (
    <div className="flex w-full items-center gap-2 px-1.5">
      <span
        aria-hidden="true"
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-destructive/10 text-xs font-bold text-destructive"
      >
        P
      </span>
      <span className="min-w-0 flex-1 truncate text-xs font-semibold uppercase tracking-wider text-destructive">
        Platform admin
      </span>
    </div>
  );
}
