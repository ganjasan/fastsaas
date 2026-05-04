/**
 * Vitest unit tests for the pinned-org store.
 *
 * Tests do not touch the API; they exercise the imperative `orgPin` shim
 * (used by the orval mutator) and the React `useOrgStore` hook in
 * isolation.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { orgPin, useOrgStore } from "./orgStore";

describe("orgStore", () => {
  beforeEach(() => {
    // Each test starts from a clean slate — drop persisted state too.
    useOrgStore.setState({ currentOrgSlug: null });
    if (typeof window !== "undefined" && window.localStorage) {
      window.localStorage.clear();
    }
  });

  afterEach(() => {
    useOrgStore.setState({ currentOrgSlug: null });
  });

  it("starts with null slug", () => {
    // GIVEN a fresh store
    // WHEN we read the slug via the imperative shim
    // THEN it is null
    expect(orgPin.get()).toBeNull();
  });

  it("setCurrentOrgSlug updates both the React hook and the imperative shim", () => {
    // GIVEN a fresh store
    // WHEN we call setCurrentOrgSlug
    useOrgStore.getState().setCurrentOrgSlug("acme");
    // THEN both views agree
    expect(orgPin.get()).toBe("acme");
    expect(useOrgStore.getState().currentOrgSlug).toBe("acme");
  });

  it("orgPin.set mirrors useOrgStore.setCurrentOrgSlug", () => {
    // GIVEN a fresh store
    // WHEN we use orgPin.set (the path the orval mutator wouldn't use, but
    //      kept symmetric so a test can drive state without React)
    orgPin.set("globex");
    // THEN useOrgStore observes the same slug
    expect(useOrgStore.getState().currentOrgSlug).toBe("globex");
  });

  it("clearing the slug propagates to the shim", () => {
    // GIVEN a pinned slug
    orgPin.set("acme");
    // WHEN we set it back to null
    orgPin.set(null);
    // THEN reads return null again
    expect(orgPin.get()).toBeNull();
  });
});
