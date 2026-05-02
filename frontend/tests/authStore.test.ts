import { beforeEach, describe, expect, test } from "vitest";

import type { CurrentActor } from "@/api/generated/fastSaaS.schemas";
import { tokenStore, useAuthStore } from "@/features/auth/lib/authStore";

const SAMPLE_ACTOR: CurrentActor = {
  actor_id: "00000000-0000-0000-0000-000000000001",
  actor_type: "HUMAN",
  parent_actor_id: null,
  email: "user@example.com",
  email_verified: true,
};

describe("useAuthStore", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null, currentActor: null });
  });

  test("setSession populates both token and actor in one call", () => {
    // GIVEN an empty store
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().currentActor).toBeNull();

    // WHEN setSession is called
    useAuthStore.getState().setSession("AT-1", SAMPLE_ACTOR);

    // THEN both fields are written
    expect(useAuthStore.getState().accessToken).toBe("AT-1");
    expect(useAuthStore.getState().currentActor).toEqual(SAMPLE_ACTOR);
  });

  test("clear wipes accessToken and currentActor together", () => {
    // GIVEN a populated store
    useAuthStore.getState().setSession("AT-2", SAMPLE_ACTOR);

    // WHEN clear is called
    useAuthStore.getState().clear();

    // THEN both fields revert to null
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().currentActor).toBeNull();
  });

  test("setAccessToken updates only the token", () => {
    // GIVEN a populated store
    useAuthStore.getState().setSession("AT-3", SAMPLE_ACTOR);

    // WHEN setAccessToken replaces the token
    useAuthStore.getState().setAccessToken("AT-3-rotated");

    // THEN the token is replaced and the actor is preserved
    expect(useAuthStore.getState().accessToken).toBe("AT-3-rotated");
    expect(useAuthStore.getState().currentActor).toEqual(SAMPLE_ACTOR);
  });

  test("tokenStore shim reads and writes the same Zustand state", () => {
    // GIVEN a token written via the imperative shim
    tokenStore.setAccessToken("AT-via-shim");

    // THEN the Zustand store sees it
    expect(useAuthStore.getState().accessToken).toBe("AT-via-shim");
    expect(tokenStore.getAccessToken()).toBe("AT-via-shim");

    // AND clear from the shim wipes the store
    tokenStore.clear();
    expect(useAuthStore.getState().accessToken).toBeNull();
  });
});
