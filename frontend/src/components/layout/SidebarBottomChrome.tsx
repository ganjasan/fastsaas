/**
 * Sidebar bottom-chrome — Status pill, Help, Changelog, Collapse toggle.
 *
 * Status is static "All systems operational" in v1; it'll wire to
 * `/api/admin/health` once issue #20 lands.
 *
 * Help and Changelog are placeholder links (`#`) — both turn into real
 * destinations as those surfaces ship.
 *
 * Collapse toggle uses the Shell context to flip the desktop rail between
 * full-width and icon-only.
 */
import { ChevronLeft, FileText, HelpCircle } from "lucide-react";

import { useShellContext } from "@/components/layout/Shell";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils/cn";

interface SidebarBottomChromeProps {
  collapsed?: boolean;
}

export function SidebarBottomChrome({ collapsed = false }: SidebarBottomChromeProps) {
  const { setCollapsed } = useShellContext();

  return (
    <div className="flex flex-col gap-2 text-xs text-muted-foreground">
      {!collapsed && (
        <div className="flex items-center gap-2 px-1.5">
          <span aria-hidden="true" className="h-2 w-2 rounded-full bg-emerald-500" />
          <span>All systems operational</span>
        </div>
      )}

      <div
        className={cn(
          "flex items-center gap-1",
          collapsed ? "flex-col" : "flex-row justify-between",
        )}
      >
        {!collapsed && (
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="flex h-7 items-center gap-1 rounded px-2 hover:bg-accent hover:text-foreground"
              title="Changelog (coming soon)"
              onClick={() => {
                // TODO: link to the published changelog when one exists.
              }}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>Changelog</span>
            </button>
            <button
              type="button"
              className="flex h-7 items-center gap-1 rounded px-2 hover:bg-accent hover:text-foreground"
              title="Help (coming soon)"
              onClick={() => {
                // TODO: link to support / docs.
              }}
            >
              <HelpCircle className="h-3.5 w-3.5" />
              <span>Help</span>
            </button>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 shrink-0"
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          onClick={() => setCollapsed(!collapsed)}
        >
          <ChevronLeft className={cn("h-4 w-4 transition-transform", collapsed && "rotate-180")} />
        </Button>
      </div>
    </div>
  );
}
