/**
 * Dashboard top bar — hosts the org switcher, theme-mode toggle, and the
 * user menu (current actor + logout). Mobile sidebar trigger is rendered
 * at the leading edge.
 */
import { useNavigate } from "@tanstack/react-router";
import { LogOut, User } from "lucide-react";

import { useLogoutAuthLogoutPost } from "@/api/generated/auth/auth";
import { ThemeModeToggle } from "@/components/layout/ThemeModeToggle";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useAuthStore } from "@/features/auth/lib/authStore";
import { OrgSwitcher } from "@/features/orgs/components/OrgSwitcher";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export function Topbar() {
  const actor = useAuthStore((s) => s.currentActor);
  const clearAuth = useAuthStore((s) => s.clear);
  const clearOrg = useOrgStore((s) => s.setCurrentOrgSlug);
  const navigate = useNavigate();
  const logout = useLogoutAuthLogoutPost();

  const handleLogout = async (): Promise<void> => {
    try {
      await logout.mutateAsync();
    } finally {
      clearAuth();
      clearOrg(null);
      void navigate({ to: "/auth/login" });
    }
  };

  return (
    <header className="flex h-14 items-center justify-between border-b bg-background px-4 lg:px-6">
      <div className="flex items-center gap-3">
        <OrgSwitcher />
      </div>
      <div className="flex items-center gap-2">
        <ThemeModeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="User menu">
              <User className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-[12rem]">
            {actor && (
              <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                {actor.email ?? actor.actor_id}
              </DropdownMenuLabel>
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={handleLogout} className="text-destructive">
              <LogOut className="mr-2 h-4 w-4" /> Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
