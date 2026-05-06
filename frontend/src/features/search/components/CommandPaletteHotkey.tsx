/**
 * Window-level Cmd+K / Ctrl+K listener that toggles the palette.
 * Mounted by both AppShell and AdminShell so the hotkey works on
 * every authenticated route.
 */
import { useEffect } from "react";

import { useSearchStore } from "../searchStore";

export function CommandPaletteHotkey(): null {
  const toggle = useSearchStore((s) => s.toggle);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isHotkey = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (!isHotkey) return;
      e.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [toggle]);

  return null;
}
