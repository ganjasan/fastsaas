/**
 * Search trigger — opens the global ⌘K palette. The button shows the
 * shortcut hint and matches the Render aesthetic; Cmd/Ctrl+K opens
 * the same palette via `<CommandPaletteHotkey>`.
 */
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useSearchStore } from "@/features/search";

export function SearchTrigger() {
  const setOpen = useSearchStore((s) => s.setOpen);
  return (
    <Button
      variant="outline"
      size="sm"
      className="hidden h-8 gap-2 px-3 text-muted-foreground hover:text-foreground sm:inline-flex"
      onClick={() => setOpen(true)}
      aria-label="Search"
    >
      <Search className="h-4 w-4" />
      <span className="text-sm">Search</span>
      <kbd className="ml-2 hidden rounded border bg-muted px-1.5 py-0.5 text-[0.65rem] font-medium text-muted-foreground lg:inline-block">
        ⌘K
      </kbd>
    </Button>
  );
}
