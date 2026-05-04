/**
 * Compact dropdown listing the orgs the caller is a member of and pinning the
 * selected slug into `useOrgStore` so subsequent API calls carry `X-Org`.
 *
 * Rendered in the dashboard shell. Hidden when the caller has no orgs (the
 * empty-state on /orgs covers that path).
 */
import { Link } from "@tanstack/react-router";

import { useListMyOrgsOrgsGet } from "@/api/generated/orgs/orgs";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export function OrgSwitcher() {
  const { data: orgs } = useListMyOrgsOrgsGet();
  const currentSlug = useOrgStore((s) => s.currentOrgSlug);
  const setSlug = useOrgStore((s) => s.setCurrentOrgSlug);

  if (!orgs || orgs.length === 0) return null;
  const current = orgs.find((o) => o.slug === currentSlug) ?? orgs[0];
  if (!current) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm">
          {current.name}
          <span className="ml-2 text-xs text-muted-foreground">{current.role}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Your organisations</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {orgs.map((o) => (
          <DropdownMenuItem
            key={o.slug}
            onSelect={() => setSlug(o.slug)}
            className={o.slug === currentSlug ? "font-semibold" : undefined}
          >
            <span className="truncate">{o.name}</span>
            <span className="ml-auto text-xs text-muted-foreground">{o.role}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/orgs/new">Create new organisation</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
