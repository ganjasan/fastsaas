/**
 * Dashboard sidebar — collapsible at `lg:` and above; renders as a Sheet
 * (slide-in drawer) below `lg`. Active link highlighting via TanStack
 * Router's `useMatchRoute`. Collapsed state persists in localStorage.
 */
import { Link, useParams } from "@tanstack/react-router";
import { ChevronLeft, FolderKanban, LayoutDashboard, Menu, Settings } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { cn } from "@/lib/utils/cn";

const SIDEBAR_COLLAPSED_KEY = "fastsaas.appShell.sidebarCollapsed";

interface NavItem {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
}

function buildNav(slug: string): NavItem[] {
  return [
    { to: `/orgs/${slug}`, label: "Overview", icon: LayoutDashboard },
    { to: `/orgs/${slug}/projects`, label: "Projects", icon: FolderKanban },
    { to: `/orgs/${slug}/settings/members`, label: "Settings", icon: Settings },
  ];
}

function NavLinks({
  items,
  collapsed,
  onNavigate,
}: {
  items: NavItem[];
  collapsed: boolean;
  onNavigate?: () => void;
}) {
  return (
    <nav className="flex flex-col gap-1 px-2">
      {items.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          activeOptions={{ exact: false }}
          activeProps={{ className: "bg-accent text-accent-foreground" }}
          onClick={onNavigate}
          className={cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            "text-muted-foreground hover:bg-accent hover:text-accent-foreground",
            collapsed && "justify-center px-2",
          )}
        >
          <item.icon className="h-4 w-4 shrink-0" />
          {!collapsed && <span>{item.label}</span>}
        </Link>
      ))}
    </nav>
  );
}

export function Sidebar() {
  const params = useParams({ strict: false }) as { slug?: string };
  const slug = params.slug ?? "";
  const items = buildNav(slug);

  const [collapsed, setCollapsed] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === "true";
  });
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "true" : "false");
  }, [collapsed]);

  return (
    <>
      {/* Desktop ≥lg: persistent rail */}
      <aside
        className={cn(
          "hidden border-r bg-background lg:flex lg:flex-col lg:shrink-0 transition-[width] duration-200",
          collapsed ? "lg:w-16" : "lg:w-60",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b px-3">
          {!collapsed && <span className="text-sm font-semibold">FastSaaS</span>}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            onClick={() => setCollapsed((c) => !c)}
          >
            <ChevronLeft
              className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")}
            />
          </Button>
        </div>
        <div className="flex-1 overflow-y-auto py-3">
          <NavLinks items={items} collapsed={collapsed} />
        </div>
      </aside>

      {/* Mobile <lg: drawer */}
      <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
        <SheetTrigger asChild>
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
            <Menu className="h-5 w-5" />
          </Button>
        </SheetTrigger>
        <SheetContent side="left" className="w-60 p-0">
          <SheetTitle className="border-b px-4 py-3 text-sm font-semibold">FastSaaS</SheetTitle>
          <div className="py-3">
            <NavLinks items={items} collapsed={false} onNavigate={() => setDrawerOpen(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
