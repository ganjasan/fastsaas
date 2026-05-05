/**
 * Topbar control for the per-user theme mode (light / dark / system).
 * Writes to `useThemeStore`; the active mode is rendered via the icon.
 */
import { Monitor, Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useThemeContext } from "@/features/theme/ThemeProvider";
import { ThemeModeDefault } from "@/lib/theme";

export function ThemeModeToggle() {
  const { resolvedMode, userMode, setUserMode } = useThemeContext();

  // Icon reflects the resolved mode (so `system` shows current OS state).
  const ResolvedIcon =
    userMode === ThemeModeDefault.system ? Monitor : resolvedMode === "dark" ? Moon : Sun;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Theme mode">
          <ResolvedIcon className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => setUserMode(ThemeModeDefault.light)}>
          <Sun className="mr-2 h-4 w-4" /> Light
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setUserMode(ThemeModeDefault.dark)}>
          <Moon className="mr-2 h-4 w-4" /> Dark
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => setUserMode(ThemeModeDefault.system)}>
          <Monitor className="mr-2 h-4 w-4" /> System
        </DropdownMenuItem>
        {userMode !== null && userMode !== ThemeModeDefault.system && (
          <DropdownMenuItem onSelect={() => setUserMode(null)}>
            Reset to org default
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
