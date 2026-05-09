# Disposable-Email-Domain Blocklist

**Type**: feature
**Priority**: medium
**Area**: backend
**Epic**: abuse-prevention
**Created**: 2026-05-09

## Description

Reject signups, magic-link requests, and password-reset requests when the email domain is on a curated list of disposable / throwaway email providers. Optional per downstream product — privacy-conscious products may keep it off so users can sign up with Firefox Relay / SimpleLogin / DuckDuckGo aliases.

## Goals

- Block obvious throwaway-email signups before they pollute the DB or burn rate-limit quota.
- Keep the list **curated and conservative** — overblocking hurts privacy-conscious legitimate users.
- Make the policy decision per-product, not per-FastSaaS — the starter kit ships the mechanism, not the policy.

## Real-world domains observed in Mapsurvey 2026-05-08 attack

- `bitoini.com` — disposable email service
- `ellbit.com` — disposable email service
- `immenseignite.info` — disposable email service
- `mozmail.com` — Firefox Relay (disposable but **legitimate** — privacy-conscious users)

## Scope

### In Scope

- Module `backend/src/fastsaas/abuse/email_domain.py` exporting:
  - `is_disposable(email: str) -> bool` — pure function, lowercases, splits on `@`, checks against the configured set.
  - `RequireNonDisposable` FastAPI dependency that raises `HTTPException(400, code="abuse.email_domain_blocked")`.
- Configurable `AbuseSettings.disposable_email_domains: set[str]` — defaults to a curated list (≤100 entries to keep startup fast and predictable). NOT auto-pulled from a third-party feed in Phase 2 — too much volatility.
- Configurable `AbuseSettings.allowlist_email_domains: set[str]` — overrides blocklist; ships with `mozmail.com`, `simplelogin.com`, `duck.com`, `privaterelay.appleid.com`, `tutamail.com`. Users on these services are usually privacy-conscious legitimate users.
- Documentation in `docs/cookbook/abuse-prevention.md`: how to extend the list per-product, recommended sources for keeping it fresh (the well-known `disposable-email-domains/disposable-email-domains` GitHub repo).
- Audit log row written on each block.

### Out of Scope

- Real-time email-validation services (Mailgun email validator, ZeroBounce) — costs money, adds latency, third-party dep.
- DNS MX-record validation — some legitimate domains have weird MX setups.
- Auto-pull from upstream lists — too volatile; manual updates only.

## Open Questions

- Should the cookbook recommend a per-product policy decision before enabling? Yes — every product reading this should explicitly decide whether to reject `mozmail.com` users. Default state of the feature in FastSaaS = OFF; product opts in.
- Where does the curated default list live? Recommend `backend/src/fastsaas/abuse/_disposable_domains.py` as a Python set constant. Easy to audit via PR diffs.
- Edge case: email validators see `User+tag@domain.com` as same as `User@domain.com`. Domain check is unaffected — but worth noting in tests that the `User+tag` form still works.

## Related

- Epic: [abuse-prevention](epics/abuse-prevention.md)
- Sibling: feature-verify-before-account.md (orthogonal — domain check happens before the pending-signup token is issued)
- Note: Apply to all three email-emitting endpoints, not just register, otherwise an attacker shifts to `magic-link` or `password-reset` with the throwaway domains.
