/**
 * Pages registry — local nav targets the palette renders without
 * hitting the backend. Pages always live under "Pages" group, ordered
 * by registration order, filtered by each entry's `visible` predicate.
 *
 * Foundation registers the workspace dashboard, members, and project
 * list. Downstream features should register their own pages here at
 * module-load (e.g. from `features/<x>/index.ts`).
 */
import type { PageEntry } from "../types";

const _pages: PageEntry[] = [];

export function registerPage(entry: PageEntry): void {
  if (_pages.some((p) => p.id === entry.id)) {
    throw new Error(`Search Page entry "${entry.id}" already registered`);
  }
  _pages.push(entry);
}

export function pages(): readonly PageEntry[] {
  return _pages;
}

export function _resetPagesForTests(): void {
  _pages.length = 0;
}
