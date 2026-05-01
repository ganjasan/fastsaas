---
tags: [decision, status/accepted, category/security, priority/critical]
created: 2026-05-01
decided: 2026-05-01
supersedes: []
traces_to:
 related:
 - "[[ADR-009_actor-model-cti]]"
 spike: platform-saas-core-architecture-spike
 epic: the SaaS-core epic
---

# ADR-008: Auth flow — hybrid token storage, rotating refresh, OAuth providers

## Status
Accepted

## Context

`platform` ships an SPA frontend (per ADR-004) talking to a FastAPI backend. The first-impression UX is the login flow; if it's clumsy, the product is not used. At the same time, a leaked token must not give an attacker permanent access. The trade space spans token lifetimes, browser storage, magic-link semantics, and OAuth provider selection — and every choice locks the others.

Target audience for v1: small consulting firms (Acme Consulting type) and large enterprise customers (Globex type), plus solo practitioners. AGENT actors (per the FASTSAAS Actor-Centric vision) are scoped in the schema but **not exposed in v1 SaaS-core** — their flow ships with the future MCP epic.

## Decision

A coherent bundle of four sub-decisions, taken together as the v1 auth flow.

### 8a. JWT lifetime — short access + rotating refresh

- **Access token:** 15 minutes, JWT signed (RS256 or EdDSA — pick at impl time).
- **Refresh token:** 30 days, **rotating**. Each use issues a new refresh and invalidates the prior. Reuse of an old refresh blacklists the entire family in Redis and forces re-login (reuse-detection).
- **Logout:** blacklist refresh in Redis with TTL = remaining lifetime. Access tokens expire naturally within 15 minutes.

### 8b. Browser storage — hybrid

- **Access token:** in-memory only (TanStack Query state / React context). Lost on tab close; re-fetched via refresh on next start.
- **Refresh token:** httpOnly cookie, `Secure`, `SameSite=Lax`, scoped to `/auth/*` path.
- **No tokens in `localStorage` or `sessionStorage`** — XSS cannot exfiltrate either token.
- **CSRF:** SameSite=Lax covers cross-site POST; the refresh endpoint additionally requires a custom header (`X-Refresh: 1`) which a cross-site form cannot set.

### 8c. Magic-link TTLs — per purpose, single-use

| Purpose | TTL | Reuse |
|---------|-----|-------|
| Login magic-link | 15 min | single-use |
| Email verification | 24 h | single-use |
| Org invitation | 7 days | single-use |
| Password reset | 1 h | single-use |

All tokens stored as `sha256(token)` in the database; the raw token only appears in the email URL.

### 8d. OAuth providers in v1 — Google + Microsoft (M365)

- **Google:** broad coverage, all audiences.
- **Microsoft (M365):** critical for target market corporate clients (Acme Consulting, Globex).
- **Deferred:** GitHub (revisit if FASTSAAS goes public-ready), Apple (B2B-web SaaS does not need it), LinkedIn.

### 8e. Email verification before login — required

No verified email → no login (and no magic-link issued).

## Alternatives Considered

### Long-lived JWT only (no refresh)

- Simpler.
- **Rejected:** stolen token = days of access; no graceful revocation.

### `localStorage` for access token

- Simpler client code.
- **Rejected:** any XSS in the SPA exfiltrates the token. For a multi-tenant SaaS, that's an unacceptable failure mode.

### Server-session cookies (no JWT)

- Best revocation semantics.
- **Rejected:** ties the SPA to the same origin permanently and complicates eventual mobile / API consumer support; chose JWT for forward compatibility.

### GitHub OAuth in v1

- Tech-audience friendly.
- **Deferred:** ICP for v1 is target market practitioner / corporates, not developers. Re-evaluate when the public-ready audience matters.

## Consequences

### Positive

- 15-minute access window keeps the blast radius small if a token leaks.
- Refresh rotation + reuse detection turns a stolen refresh into a forced logout — defender wins.
- httpOnly refresh + in-memory access is the OWASP-recommended pattern for SPAs and resists both XSS and CSRF.
- OAuth choices are driven by the actual ICP, not generic enthusiasm.

### Negative

- Hybrid storage is more code than "just put the token in localStorage" — mitigated by the orval custom mutator (per ADR-004 + design.md #8) which centralises the dance.
- Refresh-rotation logic must handle concurrent requests gracefully (one wins, others retry once). Documented in the auth library.
- Microsoft OAuth integration is more complex than Google's (Microsoft Identity Platform vs straightforward Google OAuth). Estimated +1 day in the identity sub-issue.

## Open Questions

- JWT signing algo: RS256 (separate keypair, easy to rotate) vs EdDSA (smaller, faster). Decide in bootstrap.
- Library: lean **hand-rolled minimal** with `python-jose` + `httpx-oauth` to keep the surface understood; revisit if it grows.
- Redis key schema for blacklisted refresh families.

## References

- [[../../openspec/changes/platform-saas-core-architecture-spike/design.md|Spike design.md — Decision #4]]
- [[ADR-009_actor-model-cti]]
- OWASP cheat sheet — Token Based Authentication — https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
