/**
 * Custom orval mutator (per spike design.md §8 + ADR-008/ADR-017).
 *
 * On a 401 response we attempt a single in-flight refresh via `recoverFrom401`,
 * then retry the original request once with the new access token. If refresh
 * itself fails the user is redirected to /auth/login by `recoverFrom401`.
 *
 * Outgoing requests carry an `X-Org: <slug>` header when a slug is pinned in
 * the org store — that's how `tenants.dependencies.tenant_context` resolves
 * which org the request belongs to. Pre-tenant routes (`/auth/*`,
 * `/orgs` listing/create, `/orgs/members/accept`,
 * `/orgs/projects/accept-share`) ignore the header server-side, so it's
 * always safe to send.
 */
import { tokenStore } from "@/features/auth/lib/authStore";
import { recoverFrom401 } from "@/features/auth/lib/refreshFlow";
import { orgPin } from "@/features/orgs/lib/orgStore";

export type ApiError = { status: number; body: unknown };

interface ApiClientConfig {
  url: string;
  method: string;
  params?: Record<string, unknown>;
  data?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

async function doFetch(config: ApiClientConfig, accessToken: string | null): Promise<Response> {
  const url = new URL(config.url, window.location.origin);
  if (config.params) {
    for (const [k, v] of Object.entries(config.params)) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...config.headers,
  };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const orgSlug = orgPin.get();
  if (orgSlug && !headers["X-Org"]) headers["X-Org"] = orgSlug;

  return fetch(url, {
    method: config.method,
    headers,
    body: config.data === undefined ? undefined : JSON.stringify(config.data),
    credentials: "include",
    signal: config.signal,
  });
}

export async function apiClient<T>(config: ApiClientConfig): Promise<T> {
  let res = await doFetch(config, tokenStore.getAccessToken());

  if (res.status === 401) {
    // Auth/refresh endpoints intentionally surface 401 — never recurse there.
    const isAuthRefresh = config.url.startsWith("/auth/refresh");
    if (!isAuthRefresh) {
      const fresh = await recoverFrom401();
      if (fresh) {
        res = await doFetch(config, fresh);
      }
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err: ApiError = { status: res.status, body };
    throw err;
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
