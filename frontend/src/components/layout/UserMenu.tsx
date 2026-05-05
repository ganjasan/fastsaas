/**
 * Topbar user menu — actor email + Logout. Ported from the prior `<Topbar>`.
 */
import { useNavigate } from "@tanstack/react-router";
import { LogOut, User } from "lucide-react";

import { useLogoutAuthLogoutPost } from "@/api/generated/auth/auth";
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
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export function UserMenu() {
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
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="User menu">
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
  );
}
