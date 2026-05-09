# Honeypot fields on auth POST schemas

**Type**: feature
**Priority**: high
**Area**: backend+frontend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Add hidden honeypot fields to the three unauthenticated email-emitting auth requests. Real browsers (and well-behaved JS auto-fillers like 1Password / Bitwarden) leave the honeypot blank; naïve bots that submit every field they see fill it. Filled honeypot → silent fake-success response that **does not match an error 400 fingerprint**, so the bot moves on thinking it succeeded.

A trivial defense — but adds zero friction for users, costs nothing to implement, and reliably catches the dumber half of the bot population that doesn't run a real headless browser. Validated against Mapsurvey's Django equivalent: caught a real bot 4 minutes after deploy on 2026-05-09 (Chrome/41 on Win 7 UA, filled honeypot → 302 fake success → no User row, no email).

## Goals

- Catch unsophisticated bots without any user-visible change.
- Silently log the trigger so we can see how often it fires (data-driven tuning of CAPTCHA thresholds).
- Same "appears to succeed" fingerprint as a real success — bot has no signal that the trap exists.

## Implementation Notes

### Backend

- Pydantic mixin `HoneypotMixin` in `backend/src/fastsaas/abuse/honeypot.py` adds an optional `website: str | None = None` field. (Field name plausible enough to look real, not `_honeypot_xxx`.)
- Apply via inheritance: `class RegisterRequest(HoneypotMixin, ...)`.
- FastAPI dependency `RequireEmptyHoneypot`. If non-empty, returns a forged 202 response (matching the real `/auth/magic-link/request` and `/auth/password-reset/request` success shape) or a forged 201 (matching `/auth/register`) directly from the dependency, without entering the route body. Writes one `audit_log` row via `audit.record(..., action='abuse.honeypot_triggered', ...)`. Uses `early_response` pattern: dependency raises `HTTPException` with crafted detail body? Actually FastAPI doesn't natively support "return success from a dependency without running the route" — implementation likely needs a thin wrapper that the route checks at the top.
- Alternative cleaner pattern: route body checks `request.state.honeypot_triggered` (set by middleware) and returns the success response without invoking `service.register_user(...)`. Decide during implementation.
- Field name `"website"` is **hardcoded** as a constant `HONEYPOT_FIELD_NAME = "website"` in `backend/src/fastsaas/abuse/honeypot.py`. The `ABUSE_HONEYPOT_FIELD` configurability that the Mapsurvey design initially proposed was dropped during Phase 7 review — collisions are vanishingly unlikely (no upstream auth schema has a `website` field) and indirection costs more than it saves.

### Frontend

- React form components for register / magic-link / reset add an inline `<input type="text" name="website" tabindex="-1" autocomplete="off" aria-hidden="true">` styled `position:absolute; left:-9999px; width:1px; height:1px;` — invisible to humans, present in DOM for naïve scrapers.
- **Important**: do not use `display:none` — some bots specifically check for it as a honeypot signal. Off-screen positioning is cleaner.

### Audit + ordering

- Honeypot check fires **before** Turnstile siteverify and rate-limit increment. If a bot submits a filled honeypot, we don't waste Turnstile API calls and we don't burn rate-limit quota on the bot's IP (saving headroom for legitimate users on shared NAT).
- The audit log row records `defense='honeypot'`, IP, user-agent, the endpoint, and `detail='filled'`. **Does not record the email** (GDPR — see ADR-006/010 "minimal PII in audit").

## Why "fake-success", not 400 / 403

- Returning an error gives the bot a clear signal that the form has a hidden trap. The bot can iterate (drop fields, re-submit) until it finds the real path.
- Returning a success-shaped response makes the bot believe the email is queued and move on. We win the race.

## Out of Scope

- Honeypots on authenticated endpoints — different attack profile, not high-value.
- Behavioral analysis (typing speed, mouse-move detection) — overkill at our scale.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-registration-captcha.md, feature-registration-rate-limiting.md
- Cross-project: Mapsurvey's [Phase 7 review fix C1](../../../../Mapsurvey/openspec/changes/archive/2026-05-09-add-registration-abuse-defenses/design.md) documented the subtle bug that honeypot-in-form-clean exposes: a bot that fills the honeypot AND submits invalid form data otherwise sees a regular form-error 200, fingerprinting the trap. Honeypot must be checked from raw POST body BEFORE form validation. We replicate that lesson here in the dependency-ordering note above.
