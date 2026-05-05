/**
 * Compact workspace switcher rendered in the AppShell sidebar header.
 *
 * Two visual modes:
 * - Expanded (default): `[avatar tile] <name> ⌄` button; clicking opens a
 *   dropdown with the user's orgs + a "Create new organisation" link.
 * - Collapsed (sidebar rail at lg+): just the avatar tile; same dropdown.
 *
 * Pinning the selected slug into `useOrgStore` is unchanged from the prior
 * `<OrgSwitcher>` (the renamed component); subsequent API calls inherit the
 * `X-Org` header through the orval mutator.
 */
import { Link } from "@tanstack/react-router";
import { ChevronsUpDown } from "lucide-react";

import { useListMyOrgsOrgsGet } from "@/api/generated/orgs/orgs";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOrgStore } from "@/features/orgs/lib/orgStore";
import { cn } from "@/lib/utils/cn";

interface WorkspaceSwitcherProps {
  /** Sidebar collapse state. When true, render avatar-only. */
  collapsed?: boolean;
}

function avatarLetter(name: string): string {
  const trimmed = name.trim();
  return trimmed.length === 0 ? "?" : trimmed.charAt(0).toUpperCase();
}

export function WorkspaceSwitcher({ collapsed = false }: WorkspaceSwitcherProps) {
  const { data: orgs } = useListMyOrgsOrgsGet();
  const currentSlug = useOrgStore((s) => s.currentOrgSlug);
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  if (!orgs || orgs.length === 0) return null;
  const current = orgs.find((o) => o.slug === currentSlug) ?? orgs[0];
  if (!current) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className={cn(
          "flex w-full items-center gap-2 rounded-md p-1.5 text-left text-sm",
          "hover:bg-accent transition-colors",
          collapsed && "justify-center",
        )}
      >
        <span
          aria-hidden="true"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary text-xs font-semibold text-primary-foreground"
        >
          {avatarLetter(current.name)}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 truncate font-medium">{current.name}</span>
            <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          </>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-60" sideOffset={4}>
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Your organisations
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {orgs.map((o) => (
          <DropdownMenuItem
            key={o.slug}
            onSelect={() => setSlug(o.slug)}
            className={o.slug === currentSlug ? "font-semibold" : undefined}
          >
            <span
              aria-hidden="true"
              className="mr-2 flex h-6 w-6 shrink-0 items-center justify-center rounded bg-muted text-[0.65rem] font-semibold"
            >
              {avatarLetter(o.name)}
            </span>
            <span className="truncate">{o.name}</span>
            <span className="ml-auto pl-2 text-xs text-muted-foreground">{o.role}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/orgs/new">+ Create new organisation</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
