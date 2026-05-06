/**
 * Smoke tests for the per-workspace recent-search store.
 *
 * Covers the two non-obvious behaviours: dedup-by-id (clicking the same
 * project twice keeps a single entry, just floats it to the top) and
 * the max-recents cap so a long history doesn't bloat localStorage.
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useSearchStore } from "./searchStore";
import type { SearchHit } from "./types";

function hit(overrides: Partial<SearchHit> = {}): SearchHit {
  return {
    entity_type: "project",
    entity_id: "p-1",
    title: "Project 1",
    subtitle: "p-1",
    href: "/orgs/acme/projects/p-1",
    ...overrides,
  };
}

describe("searchStore", () => {
  beforeEach(() => {
    // Each test starts with the store cleared.
    useSearchStore.setState({ open: false, recentByWorkspace: {} });
  });

  it("returns the seeded hit WHEN recordRecent runs once GIVEN an empty store", () => {
    // GIVEN an empty store
    const { recordRecent, getRecents } = useSearchStore.getState();
    // WHEN one hit is recorded for workspace "acme"
    recordRecent("acme", hit());
    // THEN getRecents returns exactly that hit
    expect(getRecents("acme")).toHaveLength(1);
    expect(getRecents("acme")[0]?.entity_id).toBe("p-1");
  });

  it("dedups by entity_type+id and floats the duplicate to the top WHEN re-recorded", () => {
    // GIVEN a store seeded with hits A, B, C in order
    const { recordRecent, getRecents } = useSearchStore.getState();
    recordRecent("acme", hit({ entity_id: "a", title: "A" }));
    recordRecent("acme", hit({ entity_id: "b", title: "B" }));
    recordRecent("acme", hit({ entity_id: "c", title: "C" }));
    // WHEN A is recorded again
    recordRecent("acme", hit({ entity_id: "a", title: "A" }));
    // THEN A is at index 0 and the list still has 3 entries (no duplicate)
    const recents = getRecents("acme");
    expect(recents).toHaveLength(3);
    expect(recents.map((r) => r.entity_id)).toEqual(["a", "c", "b"]);
  });

  it("scopes recents by workspace slug WHEN two workspaces record different hits", () => {
    // GIVEN one hit in workspace "acme" and another in "globex"
    const { recordRecent, getRecents } = useSearchStore.getState();
    recordRecent("acme", hit({ entity_id: "acme-1", title: "Acme project" }));
    recordRecent("globex", hit({ entity_id: "globex-1", title: "Globex project" }));
    // WHEN getRecents is called for each workspace
    // THEN each workspace's list contains only its own hit — no commingling
    expect(getRecents("acme")).toHaveLength(1);
    expect(getRecents("acme")[0]?.entity_id).toBe("acme-1");
    expect(getRecents("globex")).toHaveLength(1);
    expect(getRecents("globex")[0]?.entity_id).toBe("globex-1");
  });

  it("caps recents at the configured maximum WHEN more hits than the cap are recorded", () => {
    // GIVEN a store seeded with 12 distinct hits (cap is 8 inside the store)
    const { recordRecent, getRecents } = useSearchStore.getState();
    for (let i = 0; i < 12; i += 1) {
      recordRecent("acme", hit({ entity_id: `p-${i}`, title: `P${i}` }));
    }
    // WHEN getRecents is called
    // THEN the list is exactly the cap length, with the oldest entries dropped
    const recents = getRecents("acme");
    expect(recents).toHaveLength(8);
    // Most-recent-first: p-11 at index 0, p-4 at index 7.
    expect(recents[0]?.entity_id).toBe("p-11");
    expect(recents[recents.length - 1]?.entity_id).toBe("p-4");
  });
});
