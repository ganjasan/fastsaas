# Verify-before-account flow rewrite

**Type**: feature
**Priority**: high
**Area**: backend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Move the `User` row insert from "registration form submitted" to "verification token consumed". Today (`backend/src/fastsaas/identity/service.py:130 register_user`), a successful POST to `/auth/register` immediately creates the actor + user with `email_verified=False`, then queues the verification email. A bot whose request slips past Turnstile + rate-limit + honeypot still pollutes the DB.

After this change: the registration form stores a short-lived **pending signup token** (signed payload, in-cache or in a small audit table) and queues the email. The `User` row is created **only** when the recipient clicks the link and the token is consumed. If they never click, nothing persists.

## Goals

- Stop bot-bypass-of-Phase-1 from polluting `users` / `actors`.
- Make the registration-conversion funnel measurable (`registration_attempts` vs `accounts_created` becomes a real funnel).
- Reduce admin cleanup burden for incidents that slip past defenses.
- Align the `register` flow with the existing `magic-link/request` flow, which already uses this pattern (no User created until consume).

## Why this is Phase 2, not Phase 1

Phase 1 (Turnstile + rate-limit + honeypot) stops the **outbound spam attack** — the user-facing emergency. This change stops the **DB pollution side-effect**. They are independent — both should ship, but the email-cannon problem is the one that costs SMTP reputation.

This change is also more invasive: it touches the auth flow, requires a pending-signup mechanism, and needs careful test coverage on edge cases (link expiry, double-clicking, account already exists with that email, race condition on two clicks within milliseconds).

## Scope

### In Scope

- New mechanism for pending signups. Two options to evaluate:
  1. **Signed token, no DB row** — `itsdangerous`-style signed payload encoding `(email, password_hash, salt, expires_at)`. Token is the verification link parameter; consume = decrypt + create `User`. Pro: zero schema work. Con: password hash in token (acceptable, it's a hash, but feels weird).
  2. **`pending_signup` table** — short-lived row with `(token_hash, email, password_hash, expires_at)`. Token is the row's verification key. Consume = atomic `SELECT … FOR UPDATE` + `INSERT INTO users` + `DELETE pending_signup` in one tx. Pro: auditable, easy to purge. Con: requires migration.

   Recommend Option 2 — the auditability + purge-job clarity outweighs the migration cost.
- New endpoint `POST /auth/register/consume` (or reuse `POST /auth/verify-email` with new semantics if backward compat is acceptable on this branch).
- Throttling: re-submitting the same email within the token TTL re-sends the link to the existing pending row, never creates a duplicate. Prevents the form itself from being weaponized for email floods.
- UX: clear messaging on the registration page ("we sent you a link, click it to finish").
- UX: "I never got the email" → single resend button, rate-limited.
- Backward compat: existing `email_verified=False` users transition. The migration should keep them as-is — only NEW signups go through pending-table. After 30 days the legacy path can be retired.

### Out of Scope

- Login flow changes — orthogonal.
- Password reset flow — already token-based, doesn't need this rework.
- Migration of existing unverified users — handle via the unverified-purge feature once it lands.

## Open Questions

- **Token TTL**: 24h matches industry standard. Configurable per `AbuseSettings`. OK?
- **Pending table cardinality**: in pathological abuse scenarios, this table could grow unbounded if the auto-purge cron lags. Add an opportunistic cleanup on every successful consume? Yes — cheap, prevents runaway growth.
- **Two-step or one-step UX?** Some products prefer "auto-login on email click → set password on next page" (no password at registration). FastSaaS's existing pattern asks for password upfront — keep that behavior to minimize blast radius of this change.
- **Race condition: two clicks in <100ms** — the `SELECT … FOR UPDATE` in option 2 handles this. Document the test case.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-unverified-account-purge.md (becomes "purge stale pending_signup rows" after this lands — even simpler)
- Aligns with: existing magic-link flow (pattern reference)

## Anti-pattern to avoid

Mapsurvey's design notes warn that **email verification alone (this Phase-2 item) is NOT enough** — the verification email is the very thing the attacker wants Mapsurvey to send. We must keep CAPTCHA / honeypot / rate-limit (Phase 1) in place as the load-bearing defense; this feature is purely about reducing DB pollution and improving funnel observability.
