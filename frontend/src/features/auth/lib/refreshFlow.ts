/**
 * Refresh-on-401 flow shared by every API call.
 *
 * Per auth-flows §"Concurrent 401s share one refresh in flight" + ADR-008 §8b:
 * concurrent 401s collapse to a SINGLE in-flight `POST /auth/refresh`; if it
 * succeeds, the new access token is stored and every awaiting caller is
 * resumed; if it fails, the store is cleared and the user is bumped to the
 * login page.
 */
import { useAuthStore } from "@/features/auth/lib/authStore";

let inFlight: Promise<string | null> | null = null;

/** Path the user is bounced to when the refresh attempt fails. */
const LOGIN_PATH = "/auth/login";

async function performRefresh(): Promise<string | null> {
  const res = await fetch("/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: { "X-Refresh": "1" },
  });
  if (!res.ok) return null;
  const body = (await res.json()) as { access_token?: string };
  return body.access_token ?? null;
}

/**
 * Returns a fresh access token or null. Concurrent callers within the same
 * tick share the same network round-trip.
 */
export function refreshAccessToken(): Promise<string | null> {
  if (inFlight) return inFlight;
  inFlight = performRefresh().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** Hook used by `apiClient` after a 401: refresh once, retry once, else redirect. */
export async function recoverFrom401(): Promise<string | null> {
  const fresh = await refreshAccessToken();
  if (fresh) {
    useAuthStore.getState().setAccessToken(fresh);
    return fresh;
  }
  // Refresh failed — bail out. Don't loop the user through login if they're
  // already on a public auth page.
  useAuthStore.getState().clear();
  if (typeof window !== "undefined" && !window.location.pathname.startsWith("/auth/")) {
    window.location.assign(LOGIN_PATH);
  }
  return null;
}
