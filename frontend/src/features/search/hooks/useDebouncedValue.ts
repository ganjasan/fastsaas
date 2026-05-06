/**
 * Tiny debounced-value hook — used by the palette to avoid issuing a
 * `/search` request on every keystroke. Mirrors the standard "delayed
 * mirror of a state value" pattern; nothing in the ecosystem we depend
 * on already provides one.
 */
import { useEffect, useState } from "react";

export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(t);
  }, [value, delayMs]);
  return debounced;
}
