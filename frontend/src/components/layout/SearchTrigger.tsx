/**
 * Search trigger — placeholder no-op for v1. The button shows the `⌘K`
 * shortcut hint and matches the Render aesthetic; clicking it does nothing
 * yet. The real command palette is its own epic; this component pins the
 * surface so the future palette ships behind a familiar trigger.
 */
import { Search } from "lucide-react";

import { Button } from "@/components/ui/button";

export function SearchTrigger() {
  return (
    <Button
      variant="outline"
      size="sm"
      className="hidden h-8 gap-2 px-3 text-muted-foreground hover:text-foreground sm:inline-flex"
      onClick={() => {
        // TODO: open command palette (separate epic).
      }}
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
