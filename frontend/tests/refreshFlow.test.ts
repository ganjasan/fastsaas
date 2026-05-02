import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { useAuthStore } from "@/features/auth/lib/authStore";
import { recoverFrom401, refreshAccessToken } from "@/features/auth/lib/refreshFlow";

const okResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });

const failResponse = (status: number) =>
  new Response(JSON.stringify({ detail: { code: "auth.refresh_unknown" } }), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("refreshAccessToken — single-in-flight invariant", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null, currentActor: null });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("concurrent callers share one network round-trip", async () => {
    // GIVEN a stubbed /auth/refresh that succeeds once
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(okResponse({ access_token: "AT-fresh" }));

    // WHEN three callers call refreshAccessToken in the same tick
    const [a, b, c] = await Promise.all([
      refreshAccessToken(),
      refreshAccessToken(),
      refreshAccessToken(),
    ]);

    // THEN one fetch is performed, and all callers see the same token
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(a).toBe("AT-fresh");
    expect(b).toBe("AT-fresh");
    expect(c).toBe("AT-fresh");
  });

  test("after the in-flight settles, a fresh call performs a new fetch", async () => {
    // GIVEN a stub that returns a different token each time
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(okResponse({ access_token: "AT-1" }))
      .mockResolvedValueOnce(okResponse({ access_token: "AT-2" }));

    // WHEN refreshAccessToken is called twice serially
    const first = await refreshAccessToken();
    const second = await refreshAccessToken();

    // THEN each call dispatched its own fetch
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    expect(first).toBe("AT-1");
    expect(second).toBe("AT-2");
  });

  test("refresh returns null on non-2xx without throwing", async () => {
    // GIVEN a 401 from /auth/refresh
    vi.spyOn(globalThis, "fetch").mockResolvedValue(failResponse(401));

    // WHEN refreshAccessToken is called
    const result = await refreshAccessToken();

    // THEN it returns null (caller handles the failure)
    expect(result).toBeNull();
  });
});

describe("recoverFrom401", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: "AT-stale", currentActor: null });
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  test("on success, writes the new token into the store and returns it", async () => {
    // GIVEN /auth/refresh returns a fresh token
    vi.spyOn(globalThis, "fetch").mockResolvedValue(okResponse({ access_token: "AT-new" }));

    // WHEN recovery runs
    const result = await recoverFrom401();

    // THEN the store reflects the new token and the function returns it
    expect(result).toBe("AT-new");
    expect(useAuthStore.getState().accessToken).toBe("AT-new");
  });

  test("on failure from a non-/auth page, clears the store and redirects to /auth/login", async () => {
    // GIVEN refresh fails AND the user is on a protected page
    vi.spyOn(globalThis, "fetch").mockResolvedValue(failResponse(401));
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/dashboard", assign: assignSpy },
    });

    // WHEN recovery runs
    const result = await recoverFrom401();

    // THEN it returns null, clears the store, and redirects
    expect(result).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(assignSpy).toHaveBeenCalledWith("/auth/login");
  });

  test("on failure while ALREADY on an /auth page, does NOT redirect (no loop)", async () => {
    // GIVEN refresh fails AND the user is already on /auth/login
    vi.spyOn(globalThis, "fetch").mockResolvedValue(failResponse(401));
    const assignSpy = vi.fn();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: { pathname: "/auth/login", assign: assignSpy },
    });

    // WHEN recovery runs
    const result = await recoverFrom401();

    // THEN the store is cleared but no redirect is attempted
    expect(result).toBeNull();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(assignSpy).not.toHaveBeenCalled();
  });
});
