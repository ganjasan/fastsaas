# Epic: Abuse Prevention

**Slug**: abuse-prevention
**Created**: 2026-05-09

## Description

Defenses against automated abuse on FastSaaS's three unauthenticated email-emitting endpoints:

- `POST /auth/register` (`backend/src/fastsaas/api/auth.py:138`) — sends `email_service.send_verification`
- `POST /auth/magic-link/request` (`backend/src/fastsaas/api/auth.py:217`) — sends `email_service.send_magic_link`
- `POST /auth/password-reset/request` (`backend/src/fastsaas/api/auth.py:242`) — sends `email_service.send_password_reset`

Each endpoint accepts an email in the request body, queues a `BackgroundTasks` job to send a transactional email, and returns 201/202. **No CAPTCHA. No rate limit. No honeypot.** A bot can subscription-bomb any of the three to weaponize the FastSaaS app as an email-bomb cannon against a list of harvested victim addresses.

This is **not hypothetical**. The Mapsurvey project (Django, similar architecture) was hit on 2026-05-07/08 with 41 bot signups in 36 hours — same attack pattern: random usernames, harvested emails, several emails repeated across accounts (signature of email-bombing). Cleanup required manual SQL on production. Every burst chips at SMTP reputation, silently degrading deliverability of legitimate transactional and outbound mail. After defenses shipped to Mapsurvey on 2026-05-09, a real bot was caught **within 4 minutes of go-live** (Chrome/41 on Win 7 UA, filled honeypot).

FastSaaS is a **starter kit** — every downstream SaaS that inherits FastSaaS inherits this vulnerability. **Shipping abuse-prevention here protects all current and future products built on FastSaaS automatically**, not just one app.

## Vision

> A bot hitting any of `/auth/register`, `/auth/magic-link/request`, or `/auth/password-reset/request` on a FastSaaS-derived product cannot trigger an email send to a victim's inbox. Real users (a customer signing up, a colleague requesting magic-link, an admin resetting their password) experience zero added friction — Turnstile clears them invisibly in <1s. Downstream products can disable, retune, or replace specific defenses via config, without touching code.

## Scope

### In Scope

- CAPTCHA / Turnstile gate on the three email-emitting auth endpoints (and any future endpoint that triggers an outbound email pre-authentication).
- Per-IP rate limiting backed by Redis (already provisioned in FastSaaS for sessions).
- Honeypot fields in Pydantic request schemas + invisibly-styled inputs in the React forms.
- Verify-before-account flow rewrite — do not create the User row until email is verified, so a defeated bot leaves zero DB residue.
- Disposable / throwaway-email-domain blocklist with configurable allowlist for known privacy-friendly relays (Posteo, ProtonMail, SimpleLogin, Apple Hide My Email, DuckDuckGo, Firefox Relay).
- Periodic audit-and-purge of unverified accounts that never confirm.
- Anomaly dashboard via the existing `audit_log` table (per ADR-006/010) — no new model needed.
- Cloudflare-aware client-IP detection middleware (read `CF-Connecting-IP` only when explicitly trusted).
- Configuration that lets downstream products disable or retune any defense without forking.

### Out of Scope (for this epic)

- WAF / Cloudflare Bot Management at the edge — separate infra concern.
- Account 2FA — orthogonal, different threat model.
- CAPTCHA on `/auth/login` — login brute-force is a different attack model with different UX trade-offs; will be a separate epic if needed.
- General API rate limiting beyond the three identified endpoints.

## Phases

### Phase 1: Stop the bleeding (very high priority — blocks any production rollout)

1. **Turnstile** on `/auth/register`, `/auth/magic-link/request`, `/auth/password-reset/request`. Reusable FastAPI dependency + React widget component.
2. **Per-IP rate limiting** on the same three endpoints (and Cloudflare-trusted IP middleware as prerequisite infrastructure). 3 attempts per hour per IP, 10 per day per IP, configurable.
3. **Honeypot fields** in `RegisterRequest`, `MagicLinkRequestBody`, `PasswordResetRequestBody`. Invisible to humans, filled by naïve bots → silent fake-success response, no email sent.

These three together catch ~99% of automated subscription-bombing scripts. Phase 1 is the difference between "any FastSaaS product is a free email cannon" and "FastSaaS products are not weaponizable."

### Phase 2: Reduce DB pollution and abuse surface

4. **Verify-before-account** — refactor `register_user` so it does NOT create a `User` row until the verification token is consumed. Until then, only a short-lived `pending_signup` token (signed, in-cache or in a small audit table) records the intent. Defeated bots leave zero residue. Aligns with the existing magic-link pattern (no User created until consume).
5. **Disposable-email-domain blocklist** — reject signups whose email domain is on a curated list (`bitoini.com`, `ellbit.com`, `immenseignite.info`, `mozmail.com` only when not on the allowlist, etc.). Configurable per-product so a downstream SaaS can opt out.
6. **Auto-purge of unverified accounts** that never confirm within N days. After Phase 2.4, this becomes "purge stale `pending_signup` tokens" — even simpler.

### Phase 3: Operational hardening

7. **Signup anomaly dashboard** — admin view that surfaces registration spikes, IP clusters, username-pattern anomalies. Reuses the existing `audit_log` table — every triggered defense writes one row via `audit.record(...)` per ADR-010, so the dashboard is a query, not a new schema.

## Real-World Driver

**Mapsurvey 2026-05-07/08 incident.** 41 bot signups in 36 hours; emails harvested from US, DE, UK, NL, AU domains; some emails repeated 2-3x; nobody logged in after registration; nobody created surveys. Manual cleanup took 30 minutes of SQL on production. Bot signups continued at lower volume even after cleanup until defenses shipped.

**Mapsurvey post-deploy result on 2026-05-09**: real bot caught within 4 minutes (`ip=31.40.204.150`, Chrome/41 on Win 7 UA, filled honeypot). Defense-in-depth works.

FastSaaS-derived products will face the same attack class. The cost of inaction = degraded SMTP reputation = legitimate transactional email (verification, magic-link, password reset, project-share invitation) starts landing in spam folders. The starter-kit design contract — "downstream products inherit hardened auth out of the box" — requires this.

## Architectural shape (preview)

The implementation lives in a new module `backend/src/fastsaas/abuse/`:

```
backend/src/fastsaas/abuse/
├── __init__.py
├── captcha.py        # verify_turnstile() pure function + FastAPI dependency
├── client_ip.py      # client_ip(request) — Cloudflare-aware
├── honeypot.py       # honeypot Pydantic mixin + check helper
├── ratelimit.py      # FastAPI dependency, fastapi-limiter-backed
├── middleware.py     # CloudflareIPMiddleware (mounted in main.py)
└── service.py        # log_abuse_event(...) → audit.record(...) wrapper
```

Each Phase 1 defense is a **FastAPI dependency** that downstream products can include or omit per route, or override entirely with their own implementation. Settings live under one `AbuseSettings` Pydantic config class so a product can disable/retune the whole epic with a single env-var block.

The abuse module **reuses the existing audit_log table** via `audit.record(...)` — no new model, no migration beyond existing audit infra. This keeps FastSaaS aligned with ADR-006 (one persistence story for both audit and abuse) and makes Phase 3 dashboard a one-query addition rather than a new schema.

## Related Backlog Items

- feature-registration-captcha.md — Phase 1 item 1 (Turnstile)
- feature-registration-rate-limiting.md — Phase 1 item 2 (rate limit)
- feature-registration-honeypot.md — Phase 1 item 3 (honeypot)
- feature-verify-before-account.md — Phase 2 item 4 (no-User-until-verified)
- feature-disposable-email-blocklist.md — Phase 2 item 5
- feature-unverified-account-purge.md — Phase 2 item 6
- improvement-signup-anomaly-dashboard.md — Phase 3 item 7

## Blocks / Blocked By

- **Blocks**: Public-internet rollout of any FastSaaS-derived product. A SaaS without these defenses is a free email cannon; not a defensible posture for any deployment that reaches the open internet. Internal-only deployments behind a corporate firewall MAY skip Phase 1 with explicit risk acknowledgment.
- **Blocked by**: Nothing. Phase 1 can ship in days. The work is small and well-scoped.

## Notes for downstream products

Every downstream SaaS that inherits FastSaaS gets these defenses for free **once the abuse module is on `main`**. Specific configuration each product MUST decide:

- Cloudflare Turnstile site/secret keys (free tier covers most products).
- `CLOUDFLARE_TRUSTED=True` only when actually deployed behind Cloudflare. False on any other CDN or direct exposure — the header would be spoofable.
- Per-product rate-limit tuning. Defaults (3/h, 10/d) suit a low-volume SaaS. High-traffic products may relax these and rely on Turnstile + honeypot for the bot blocking.
- Whether to enable the disposable-email blocklist (privacy-conscious products may keep it off to allow Firefox Relay / SimpleLogin users).

A reference Cookbook entry will live at `docs/cookbook/abuse-prevention.md` after Phase 1 ships, walking a downstream product through the 5-minute setup.

## Cross-project reference

The Mapsurvey project (`/home/artem/Documents/Projects/Mapsurvey`) shipped the Django equivalent of Phase 1 as change `add-registration-abuse-defenses` (archived 2026-05-09 as `2026-05-09-add-registration-abuse-defenses`). The OpenSpec change folder there is a useful reference for design decisions, especially:
- D2: Honeypot validation in view layer (not form `clean()`) — Phase 7 review C1 fix
- D4: Imperative `is_ratelimited()` over decorator for control over audit-write order
- D8: Hierarchical `abuse.*` loggers
- The Phase 7 quality review that surfaced two real bugs (`log_abuse_event` DB-error swallowing, honeypot+invalid-form fingerprinting)

The architectural decisions translate directly to FastAPI; the implementation strategy differs (FastAPI dependencies vs Django middleware/CBV), and FastSaaS has a richer audit infrastructure already in place which simplifies the persistence story.
