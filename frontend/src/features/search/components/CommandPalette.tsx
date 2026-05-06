/**
 * Global ⌘K palette. Composes:
 *  - Pages + Actions from `pagesRegistry` / `actionsRegistry` (always
 *    available, no backend round-trip; cmdk fuzzy-matches against
 *    label + keywords).
 *  - Backend search results via `useSearchEndpointOrgsSlugSearchGet`,
 *    fired only when the debounced query is at least 2 characters.
 *  - Recent searches per workspace from `useSearchStore`, shown when
 *    the input is empty.
 *
 * Selection navigates via TanStack router for SearchHits + Pages, or
 * runs the action's `perform()` for Actions, then closes the palette.
 */
import { useNavigate } from "@tanstack/react-router";
import { type ReactNode, useCallback, useEffect, useMemo, useState } from "react";

import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";

import { useSearchEndpointOrgsSlugSearchGet } from "@/api/generated/search/search";

import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { actions } from "../registries/actionsRegistry";
import { pages } from "../registries/pagesRegistry";
import { renderHit } from "../registries/rendererRegistry";
import { useSearchStore } from "../searchStore";
import type { ActionEntry, PageActionContext, PageEntry, SearchHit } from "../types";

const DEBOUNCE_MS = 180;
const MIN_QUERY_LEN = 2;

interface CommandPaletteProps {
  /** Active workspace slug. AppShell passes the org slug; AdminShell
   * may pass an empty string (Pages whose `visible` predicate requires
   * a workspaceSlug will then hide). */
  workspaceSlug: string;
  shell: "app" | "admin";
}

export function CommandPalette({ workspaceSlug, shell }: CommandPaletteProps): ReactNode {
  const navigate = useNavigate();
  const open = useSearchStore((s) => s.open);
  const setOpen = useSearchStore((s) => s.setOpen);
  const recordRecent = useSearchStore((s) => s.recordRecent);
  // Subscribe to the per-workspace slot directly so an unrelated workspace's
  // updates don't re-render us. Returning `?? []` from inside the selector
  // would manufacture a new array on every state read and re-render forever.
  const recentsRaw = useSearchStore((s) => s.recentByWorkspace[workspaceSlug]);
  const recents = useMemo(() => recentsRaw ?? [], [recentsRaw]);

  const [query, setQuery] = useState("");
  const debounced = useDebouncedValue(query, DEBOUNCE_MS);

  // Reset query when the dialog closes so reopens start fresh.
  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const ctx = useMemo<PageActionContext>(() => ({ workspaceSlug, shell }), [workspaceSlug, shell]);

  const visiblePages = useMemo<PageEntry[]>(
    () => pages().filter((p) => p.visible?.(ctx) ?? true),
    [ctx],
  );
  const visibleActions = useMemo<ActionEntry[]>(
    () => actions().filter((a) => a.visible?.(ctx) ?? true),
    [ctx],
  );

  const backendQuery = debounced.trim();
  const backendEnabled =
    shell === "app" && Boolean(workspaceSlug) && backendQuery.length >= MIN_QUERY_LEN;

  const { data, isFetching } = useSearchEndpointOrgsSlugSearchGet(
    workspaceSlug,
    { q: backendQuery },
    { query: { enabled: backendEnabled, staleTime: 30_000 } },
  );

  const handleHit = useCallback(
    (hit: SearchHit) => {
      recordRecent(workspaceSlug, hit);
      setOpen(false);
      // Foundation hrefs are app-relative; TanStack router happily
      // accepts them as `to` strings.
      void navigate({ to: hit.href });
    },
    [navigate, recordRecent, setOpen, workspaceSlug],
  );

  const handlePage = useCallback(
    (entry: PageEntry) => {
      setOpen(false);
      void navigate({ to: entry.href(workspaceSlug) });
    },
    [navigate, setOpen, workspaceSlug],
  );

  const handleAction = useCallback(
    async (entry: ActionEntry) => {
      try {
        await entry.perform(ctx);
      } finally {
        setOpen(false);
      }
    },
    [ctx, setOpen],
  );

  const showRecents = !backendQuery && recents.length > 0;
  const groups = data?.groups ?? [];

  return (
    <CommandDialog open={open} onOpenChange={setOpen} label="Search">
      <CommandInput
        value={query}
        onValueChange={setQuery}
        placeholder={shell === "admin" ? "Search pages…" : "Search projects, members, pages…"}
      />
      <CommandList>
        <CommandEmpty>{backendEnabled && isFetching ? "Searching…" : "No results."}</CommandEmpty>

        {showRecents ? (
          <>
            <CommandGroup heading="Recent">
              {recents.map((hit) => (
                <CommandItem
                  key={`recent:${hit.entity_type}:${hit.entity_id}`}
                  value={`recent ${hit.title} ${hit.subtitle ?? ""}`}
                  onSelect={() => handleHit(hit)}
                >
                  {renderHit(hit)}
                </CommandItem>
              ))}
            </CommandGroup>
            <CommandSeparator />
          </>
        ) : null}

        {visiblePages.length > 0 ? (
          <CommandGroup heading="Pages">
            {visiblePages.map((entry) => (
              <CommandItem
                key={entry.id}
                value={[entry.label, entry.description, ...(entry.keywords ?? [])]
                  .filter(Boolean)
                  .join(" ")}
                onSelect={() => handlePage(entry)}
              >
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm">{entry.label}</span>
                  {entry.description ? (
                    <span className="truncate text-xs text-muted-foreground">
                      {entry.description}
                    </span>
                  ) : null}
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}

        {visibleActions.length > 0 ? (
          <CommandGroup heading="Actions">
            {visibleActions.map((entry) => (
              <CommandItem
                key={entry.id}
                value={[entry.label, entry.description, ...(entry.keywords ?? [])]
                  .filter(Boolean)
                  .join(" ")}
                onSelect={() => void handleAction(entry)}
              >
                <div className="flex min-w-0 flex-col">
                  <span className="truncate text-sm">{entry.label}</span>
                  {entry.description ? (
                    <span className="truncate text-xs text-muted-foreground">
                      {entry.description}
                    </span>
                  ) : null}
                </div>
              </CommandItem>
            ))}
          </CommandGroup>
        ) : null}

        {groups.map((group) => (
          <CommandGroup key={group.entity_type} heading={group.label}>
            {group.hits.map((hit) => (
              <CommandItem
                key={`${hit.entity_type}:${hit.entity_id}`}
                value={`${group.label} ${hit.title} ${hit.subtitle ?? ""}`}
                onSelect={() => handleHit(hit)}
              >
                {renderHit(hit)}
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
