/**
 * `+ New ⌄` topbar dropdown — opens a small menu with the entity-create
 * actions available in the current scope:
 *
 * - "Create project" — links to `/orgs/{slug}/projects` with a `?new=1`
 *   query param so the Projects page opens the create dialog. Hidden when
 *   no org is pinned (e.g. on `/orgs/new` itself).
 * - "Create organisation" — links to `/orgs/new`. Always visible.
 *
 * The action set will grow as new entity types land (datasets, scenarios,
 * api keys, …); each consumer feature plugs a new entry here.
 */
import { Link } from "@tanstack/react-router";
import { ChevronDown, FolderPlus, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useOrgStore } from "@/features/orgs/lib/orgStore";

export function NewMenu() {
  const slug = useOrgStore((s) => s.currentOrgSlug);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" className="h-8 gap-1.5">
          <Plus className="h-4 w-4" />
          <span>New</span>
          <ChevronDown className="h-3 w-3 opacity-70" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {slug ? (
          <DropdownMenuItem asChild>
            <Link
              to="/orgs/$slug/projects"
              params={{ slug }}
              search={{ new: "1" }}
              className="flex items-center"
            >
              <FolderPlus className="mr-2 h-4 w-4" />
              Create project
            </Link>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem asChild>
          <Link to="/orgs/new" className="flex items-center">
            <Plus className="mr-2 h-4 w-4" />
            Create organisation
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
