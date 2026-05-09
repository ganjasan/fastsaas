# Per-IP Rate Limiting on email-emitting endpoints

**Type**: feature
**Priority**: very high
**Area**: backend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Hard per-IP rate limits on the three unauthenticated email-emitting endpoints. A defense-in-depth layer behind Turnstile (see [feature-registration-captcha.md](feature-registration-captcha.md)) — if a sophisticated attacker solves the CAPTCHA at scale, rate-limiting still caps damage.

## Goals

- Cap registration-burst impact: even with Turnstile bypassed, no single IP can send more than N verification / magic-link / reset emails per hour.
- Make automated abuse expensive: every retry costs the attacker a fresh IP rotation.
- Keep legitimate classroom / shared-NAT signups workable.

## Proposed Limits (initial — tune from production traffic)

| Endpoint | Per IP | Rationale |
|---|---|---|
| `POST /auth/register` | 3 / hour, 10 / day | Real users almost never re-register from same IP within an hour |
| `POST /auth/magic-link/request` | 5 / hour, 20 / day | Slightly higher — legitimate users may re-request if email got delayed |
| `POST /auth/password-reset/request` | 3 / hour, 10 / day | Same profile as register; abuse incentive identical |
| Aggregate (any of three) | 10 / hour, 30 / day | Catches an attacker rotating across endpoints to stay under per-endpoint limits |

All thresholds are env-configurable so downstream products can tune per their traffic profile.

## Implementation Notes

- **Library**: `fastapi-limiter` (Redis-backed, async-native). FastSaaS already provisions Redis for sessions and refresh-token tracking — no new infra.
- **Module**: `backend/src/fastsaas/abuse/ratelimit.py`. Exports a `register_rate_limit`, `magic_link_rate_limit`, `password_reset_rate_limit` dependency, plus an `aggregate_email_rate_limit` that combines the three.
- **Key function**: `client_ip(request)` from `backend/src/fastsaas/abuse/client_ip.py` — reads `request.state.cf_ip` set by `CloudflareIPMiddleware`. Single source of truth for IP detection (also used by Turnstile siteverify's `remoteip` parameter and by audit log writes).
- **Behavior on hit**: HTTP 429 with `Retry-After` header. Body returns `{"code": "abuse.rate_limited", "message": "Too many attempts. Please try again later."}` — same shape as other auth errors so the React error handler is unchanged.
- **Audit log**: writes one row via `audit.record(..., action='abuse.rate_limited', metadata={'limit': '3/h', 'endpoint': '/auth/register'}, ...)` per ADR-010.
- **Fail-open**: if Redis is unreachable, requests pass through. `try/except` around the limiter call. Honeypot + Turnstile remain in effect, so degradation is graceful, not catastrophic.

## Cloudflare-IP middleware (prerequisite)

`backend/src/fastsaas/abuse/middleware.py` adds `CloudflareIPMiddleware`. Reads `CF-Connecting-IP` and stores it on `request.state.cf_ip`, **only when `settings.abuse.cloudflare_trusted` is True** (default False for safety on dev / non-CF deployments — the header would be spoofable). Falls back to `request.client.host` otherwise. Mounted in `main.py` before route registration.

## Out of Scope

- IP geolocation blocking — too many false positives with VPN-using legitimate users.
- Per-email-prefix rate limiting (block 5+ accounts with the same `before-the-@`). Some attackers use `victim+1@gmail.com` etc; worth a Phase 2 add but not here.
- Rate limit on authenticated endpoints — different threat model.

## Open Questions

- Aggregate limit (`any of three / 10 per hour`): combine into one Redis key spanning all three endpoints, or three independent keys + a derived "any" check? Recommend independent keys + a small in-memory aggregator dependency that reads all three counters — simpler reasoning, no Lua scripts.
- Should Turnstile-failed requests also count towards rate limit? The Mapsurvey design said yes (every attempt counts) — keeps an attacker from exhausting Turnstile attempts without paying their rate budget. Adopt the same here.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-registration-captcha.md (Turnstile is the primary defense; rate-limit is defense-in-depth)
- Prerequisite: `CloudflareIPMiddleware` (delivered as part of this feature, used by other epic items)
