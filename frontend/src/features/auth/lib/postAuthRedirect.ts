/**
 * Pending post-auth redirect — survives the auth flow's intermediate
 * stops (register → verify-email → login → success) via localStorage.
 *
 * Use case: an unauthenticated user clicks a share-link and we want them
 * to land back on `/orgs/accept-share/{token}` after they sign in /
 * register. URL `?next=` would be lost when they click the verify-email
 * link from their inbox; localStorage carries it through.
 *
 * Single-shot: `consume` reads + removes in one call so a stale entry
 * can't redirect a future navigation.
 */
const KEY = "fastsaas.postAuthRedirect";

/** Allowlist of path prefixes we'll honour. Stops a malicious caller from
 * stashing an absolute URL or a destination that opens a redirect-bounce
 * onto a page the auth flow shouldn't deposit a session on. */
const ALLOWED_PREFIXES: readonly string[] = ["/orgs/accept-share/", "/orgs/accept-invite/"];

function isAllowed(path: string): boolean {
  return ALLOWED_PREFIXES.some((prefix) => path.startsWith(prefix));
}

export function setPostAuthRedirect(path: string): void {
  if (typeof window === "undefined") return;
  if (!isAllowed(path)) return;
  window.localStorage.setItem(KEY, path);
}

/** Read + clear in one call. Returns null if no redirect is pending or
 * the stored value falls outside the allowlist. */
export function consumePostAuthRedirect(): string | null {
  if (typeof window === "undefined") return null;
  const value = window.localStorage.getItem(KEY);
  if (value === null) return null;
  window.localStorage.removeItem(KEY);
  return isAllowed(value) ? value : null;
}
