/**
 * Actions registry — palette entries that perform a side effect rather
 * than navigating. Foundation registers a few convenience actions
 * (toggle theme, sign out); downstream features add their own.
 *
 * Same fail-loud contract as `pagesRegistry`. The palette filters
 * actions by `visible(ctx)` and `keywords` (cmdk handles fuzzy match
 * against label + keywords).
 */
import type { ActionEntry } from "../types";

const _actions: ActionEntry[] = [];

export function registerAction(entry: ActionEntry): void {
  if (_actions.some((a) => a.id === entry.id)) {
    throw new Error(`Search Action entry "${entry.id}" already registered`);
  }
  _actions.push(entry);
}

export function actions(): readonly ActionEntry[] {
  return _actions;
}

export function _resetActionsForTests(): void {
  _actions.length = 0;
}
