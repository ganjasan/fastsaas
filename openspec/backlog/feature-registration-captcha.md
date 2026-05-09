# Registration / Magic-link / Reset CAPTCHA (Cloudflare Turnstile)

**Type**: feature
**Priority**: very high
**Area**: backend+frontend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Add Cloudflare Turnstile to the three unauthenticated email-emitting auth endpoints in `backend/src/fastsaas/api/auth.py`:

- `POST /auth/register` (line 138)
- `POST /auth/magic-link/request` (line 217)
- `POST /auth/password-reset/request` (line 242)

This is the **load-bearing defense** of the abuse-prevention epic. Without it, every other measure (rate-limit, honeypot, verify-before-account) is at best a delay against a determined attacker.

## Goals

- Block automated subscription-bombing at the **first** outbound-mail trigger, not after the User row is created.
- Zero added friction for legitimate users — Turnstile's managed mode is invisible in the typical case.
- Pluggable per-route — downstream products can disable on internal-only routes.

## Why Turnstile (not hCaptcha or reCAPTCHA)

- Defaults to **invisible / managed** challenges. hCaptcha and reCAPTCHA more often surface visible "click the buses" puzzles, hostile to international / accessibility users.
- Free tier covers FastSaaS-product traffic comfortably.
- No Google dependency — privacy-friendlier for EU users, easier GDPR story.
- Cloudflare publishes always-pass test keys (`1x00000000000000000000AA` / `1x0000000000000000000000000000000AA`) that exercise the full code path locally — keeps Mailhog-driven dev workflow intact.

## Scope

### In Scope

- New module `backend/src/fastsaas/abuse/captcha.py` exporting:
  - `async def verify_turnstile(token: str, remote_ip: str) -> bool` — pure async function using `httpx.AsyncClient` against `https://challenges.cloudflare.com/turnstile/v0/siteverify` with a 5-second timeout. Returns `True` only on `success: true`. **Bypasses HTTP call (returns True) when `settings.abuse.turnstile_secret_key` is empty** so Mailhog dev flow works without configuring keys.
  - `RequireTurnstile` FastAPI dependency that reads the token from the request body, calls `verify_turnstile`, and raises `HTTPException(400, code="abuse.captcha_failed")` on failure.
- Pydantic field `cf_turnstile_response: str | None = None` added to `RegisterRequest`, `MagicLinkRequestBody`, `PasswordResetRequestBody`. Field is optional in the schema so dev-bypass mode works; the dependency enforces presence when secret is set.
- React widget component `frontend/src/features/auth/components/TurnstileWidget.tsx` mounted on registration, magic-link-request, and password-reset-request forms. Uses Cloudflare's `https://challenges.cloudflare.com/turnstile/v0/api.js` script via dynamic load. Site key from `import.meta.env.VITE_TURNSTILE_SITE_KEY`.
- Server-side rejection writes one `audit_log` row via `audit.record(..., action='abuse.captcha_failed', ...)` (per ADR-010).
- Settings: `AbuseSettings` Pydantic class in `fastsaas/abuse/__init__.py` with `turnstile_site_key`, `turnstile_secret_key`, plus `enabled: bool = True` for downstream-product opt-out.

### Out of Scope

- CAPTCHA on `/auth/login`, `/auth/refresh`, or `/auth/logout`.
- Survey-response / form-submission CAPTCHA (no such endpoints in FastSaaS — domain-specific to consumers).
- Custom challenge UX or fallback for users in regions Turnstile blocks (China, Iran). Default is fail-closed; if support requests surface, consider an explicit manual-review bypass.

## Implementation Notes

- FastSaaS already uses `httpx` elsewhere (`backend/src/fastsaas/identity/oauth.py`), so the dependency is already locked.
- The `RequireTurnstile` dependency must be applied BEFORE the route body executes — easy with `Depends(...)` in the route signature: `async def register(body: RegisterRequest, _: Annotated[None, Depends(RequireTurnstile)], ...)`.
- React widget should expose a callback that disables the form's submit button until a token is present, preventing accidental submits without verification.
- Site key + secret on production come from environment variables (the `12-factor` pattern FastSaaS already uses for JWT keys / Postmark / Postgres).
- Local dev: `infra/dev-secrets/.env.example` documents the always-pass test keys as defaults.

## Open Questions

- Does the React widget's script tag need to load on every auth-form page, or only when `import.meta.env.VITE_TURNSTILE_SITE_KEY` is set? Recommend: gated on the env, so a downstream product without keys gets a clean form with no Cloudflare phone-home.
- Should we expose an opt-out per route via FastAPI `Depends` defaults, or is a global `AbuseSettings.enabled` flag enough? Recommend: per-route (decorator/dep), so product authors can keep CAPTCHA on `/auth/register` but skip `/auth/magic-link/request` if they want.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Prerequisite for: feature-registration-rate-limiting (defense in depth on top of CAPTCHA), feature-verify-before-account (CAPTCHA stops the email; verify-before-account stops the DB pollution)
