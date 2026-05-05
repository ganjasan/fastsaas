/**
 * `<Shell>` — Render-style dashboard chrome primitive.
 *
 * Two consumers ride on this:
 * - `<AppShell>` (org dashboard) — workspace switcher in header, Projects + Settings nav.
 * - `<AdminShell>` (issue #19, future) — "PLATFORM ADMIN" pill in header, multi-section nav.
 *
 * Layout:
 *   ┌────────────┬──────────────────────────────────────┐
 *   │ header     │ topbar (left | right)                │
 *   │ sections…  ├──────────────────────────────────────┤
 *   │            │                                      │
 *   │            │ children                             │
 *   │            │                                      │
 *   ├────────────┤                                      │
 *   │ bottom     │                                      │
 *   └────────────┴──────────────────────────────────────┘
 *
 * On viewports below `lg`, the sidebar collapses into a Sheet drawer triggered
 * from the topbar (caller passes the trigger as part of `topbarLeft` if they
 * want it). The desktop rail collapses to icon-only when the user clicks the
 * collapse toggle in `sidebarBottom`.
 *
 * Active state: `bg-primary/10 text-primary`. Hover-only: `bg-accent`.
 * The two are intentionally distinct (D6 in design.md).
 */
import { Link, useRouterState } from "@tanstack/react-router";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { createContext, useContext, useEffect, useState } from "react";

import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { cn } from "@/lib/utils/cn";

const SIDEBAR_COLLAPSED_KEY = "fastsaas.appShell.sidebarCollapsed";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** When true, only mark active on exact URL match. Default: false (prefix match). */
  exact?: boolean;
}

export interface NavSection {
  /** UPPERCASE muted label rendered above the items. Omit for ungrouped lists. */
  label?: string;
  items: NavItem[];
}

interface ShellContextValue {
  collapsed: boolean;
  setCollapsed: (next: boolean) => void;
  drawerOpen: boolean;
  setDrawerOpen: (next: boolean) => void;
}

const ShellContext = createContext<ShellContextValue | null>(null);

/** Used by sidebar bottom-chrome (Collapse toggle) and by callers that want
 * to render a mobile-drawer trigger inside `topbarLeft`. */
export function useShellContext(): ShellContextValue {
  const ctx = useContext(ShellContext);
  if (ctx === null) {
    throw new Error("useShellContext must be used inside <Shell>");
  }
  return ctx;
}

interface ShellProps {
  /** Sidebar header. Receives `collapsed` so the consumer can render a
   * compact form (e.g. avatar-only) when the desktop rail collapses.
   * Drawer renders with `collapsed = false` regardless of rail state. */
  sidebarHeader: (collapsed: boolean) => ReactNode;
  sidebarSections: NavSection[];
  /** Sidebar bottom chrome. Same render-prop signature as `sidebarHeader`. */
  sidebarBottom?: (collapsed: boolean) => ReactNode;
  topbarLeft: ReactNode;
  topbarRight: ReactNode;
  children: ReactNode;
}

export function Shell({
  sidebarHeader,
  sidebarSections,
  sidebarBottom,
  topbarLeft,
  topbarRight,
  children,
}: ShellProps): ReactNode {
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "true" : "false");
  }, [collapsed]);

  const ctxValue: ShellContextValue = {
    collapsed,
    setCollapsed,
    drawerOpen,
    setDrawerOpen,
  };

  return (
    <ShellContext.Provider value={ctxValue}>
      <div className="flex min-h-screen bg-background text-foreground">
        {/* Desktop ≥lg: persistent sidebar */}
        <SidebarRail
          collapsed={collapsed}
          header={sidebarHeader}
          sections={sidebarSections}
          bottom={sidebarBottom}
        />

        {/* Mobile <lg: drawer */}
        <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
          <SheetContent side="left" className="w-64 p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SidebarBody
              collapsed={false}
              header={sidebarHeader}
              sections={sidebarSections}
              bottom={sidebarBottom}
              onNavigate={() => setDrawerOpen(false)}
            />
          </SheetContent>
        </Sheet>

        {/* Main column */}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex h-14 items-center justify-between gap-3 border-b bg-background px-4 lg:px-6">
            <div className="flex min-w-0 items-center gap-3">{topbarLeft}</div>
            <div className="flex items-center gap-2">{topbarRight}</div>
          </header>
          <main className="flex-1 overflow-y-auto p-6">{children}</main>
        </div>
      </div>
    </ShellContext.Provider>
  );
}

function SidebarRail({
  collapsed,
  header,
  sections,
  bottom,
}: {
  collapsed: boolean;
  header: (c: boolean) => ReactNode;
  sections: NavSection[];
  bottom?: (c: boolean) => ReactNode;
}): ReactNode {
  return (
    <aside
      className={cn(
        "hidden border-r bg-background lg:flex lg:flex-col lg:shrink-0 transition-[width] duration-200",
        collapsed ? "lg:w-16" : "lg:w-64",
      )}
    >
      <SidebarBody collapsed={collapsed} header={header} sections={sections} bottom={bottom} />
    </aside>
  );
}

function SidebarBody({
  collapsed,
  header,
  sections,
  bottom,
  onNavigate,
}: {
  collapsed: boolean;
  header: (c: boolean) => ReactNode;
  sections: NavSection[];
  bottom?: (c: boolean) => ReactNode;
  onNavigate?: () => void;
}): ReactNode {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b p-3">{header(collapsed)}</div>
      <div className="flex-1 overflow-y-auto py-3">
        {sections.map((section, idx) => (
          <SidebarSection
            // biome-ignore lint/suspicious/noArrayIndexKey: section order is the identity here
            key={idx}
            section={section}
            collapsed={collapsed}
            onNavigate={onNavigate}
          />
        ))}
      </div>
      {bottom ? <div className="border-t p-3">{bottom(collapsed)}</div> : null}
    </div>
  );
}

function SidebarSection({
  section,
  collapsed,
  onNavigate,
}: {
  section: NavSection;
  collapsed: boolean;
  onNavigate?: () => void;
}): ReactNode {
  return (
    <div className="px-2 pb-3">
      {section.label && !collapsed ? (
        <p className="mb-1 px-3 pt-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {section.label}
        </p>
      ) : null}
      <nav className="flex flex-col gap-1">
        {section.items.map((item) => (
          <SidebarLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} />
        ))}
      </nav>
    </div>
  );
}

function SidebarLink({
  item,
  collapsed,
  onNavigate,
}: {
  item: NavItem;
  collapsed: boolean;
  onNavigate?: () => void;
}): ReactNode {
  // Manual active-state computation so we can apply the brand-coloured
  // `bg-primary/10 text-primary` instead of TanStack Link's default
  // `activeProps` (which mounts after first render and flickers).
  const router = useRouterState({ select: (s) => s.location.pathname });
  const isActive = item.exact
    ? router === item.to
    : router === item.to || router.startsWith(`${item.to}/`);

  return (
    <Link
      to={item.to}
      onClick={onNavigate}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        isActive
          ? "bg-primary/10 text-primary"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
        collapsed && "justify-center px-2",
      )}
    >
      <item.icon className="h-4 w-4 shrink-0" />
      {!collapsed && <span className="truncate">{item.label}</span>}
    </Link>
  );
}

/** Hook to open the sidebar drawer from the topbar (mobile only).
 * Caller renders its own Button + `lg:hidden` class + invokes the returned
 * setter on click. */
export function useSidebarDrawer(): (open: boolean) => void {
  return useShellContext().setDrawerOpen;
}
