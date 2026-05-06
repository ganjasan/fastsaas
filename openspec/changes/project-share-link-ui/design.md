## Context

Backend already implements UC-001's per-project guest pattern (issue #3, phase 8 of multi-tenant change). Three endpoints exist + a recipient frontend route. No owner-side UI: operators must hit the API by curl, which made the feature effectively invisible.

## Goals

- Owner / admin can issue a guest invite to a project from the project's own page.
- Guest receives the email AND the inviting admin can copy the same link out-of-band (private chat, password manager) without waiting.
- Pending shares are listed + revocable from the same surface.
- Token disclosure follows the existing one-time-reveal pattern (org invitation UX).

## Non-goals

- Editing an in-flight share. Revoke + re-issue covers v1.
- Bulk shares — single-use is the UC-001 design decision.
- Granting `write/run` to a guest. Different model (#31).
- Hiding the section for non-share-capability actors. Backend gates with 403; client-side hint is a follow-up dependent on a generic `useCan` hook.

## Decisions

### D1 — `raw_token` becomes a one-time disclosure on `ProjectShareResponse`

Today the create endpoint returns `(id, project_id, email, expires_at)` — the raw token is only delivered via email. UI parity with the org-invitation flow would mean either (a) showing the recipient's email as the only confirmation (no copyable link in the UI), or (b) digging into Mailhog in dev to fish out the token. (a) is brittle UX (operator can't share the link via Slack); (b) doesn't work in production at all.

Adding `raw_token` to the create response is a one-time disclosure that mirrors how AWS access keys, GitHub PATs, and Stripe API keys all work — the secret is shown once at creation, then permanently irrecoverable (backend stores `sha256(token)`). The list endpoint (`ProjectShareItem`) deliberately omits the field.

**Rationale.** Closes the operator-UX gap without weakening the backend's hash-only storage. Symmetric with the industry pattern.

### D2 — UI lives on the project-detail page, not on a separate route

The Settings vertical-tab layout from #18 hosts org-level admin (Members, Branding). Project sharing is project-scoped, so it belongs on the project page itself, not in `/settings/...`.

Placement: a `<ProjectSharing>` `<section>` between the project header and the existing "Coming soon" placeholder. When the project page grows real content (analyses, scenarios, …), Sharing stays at the top of the right rail or moves into a Settings tab on the project page. Decision deferred until that page has real content.

**Rationale.** Project-scoped UI on the project page; Settings is for org-level concerns.

### D3 — TTL select shows 3/7/14/30 days

Backend caps TTL at 30 days and defaults to 14. The select offers (3, 7, 14 default, 30) — covers short-lived demos, week-long collaboration, fortnight default, and monthly maximum.

**Rationale.** Keeps the picker tight while spanning realistic durations.

### D4 — Capability gate stays server-side; UI hint is a follow-up

The "Sharing" section renders for any actor who can reach the project page. Members / viewers without `share:project` capability hit 403 from the API on submit. This is acceptable because:

- Members + viewers can already see other admin-flavoured sections (e.g. "Project not found" 404 paths reveal nothing); this is not a new info leak.
- Hiding the section client-side requires a generic `useCan` hook that reads the actor's bundle — out of scope for this change.
- Server enforces; UI hint is polish.

**Rationale.** Server is the source of truth. UI polish in a follow-up.

### D5 — Reveal panel is dismissible, not auto-hiding

After Save, the copyable link card stays visible until the operator clicks Dismiss (or navigates away). Auto-hiding after N seconds risks the operator missing it.

**Rationale.** Operator-controlled visibility on a one-shot disclosure beats a timer.

## Risks / trade-offs

- **`raw_token` in HTTP response body** — exposed over HTTPS in production, so no new threat. Logged in HTTP-access logs if logging captures bodies (unlikely in our setup; FastAPI logs status + path by default). Worth a CLAUDE.md note for downstream operators.
- **Clipboard API permission** — `navigator.clipboard.writeText` requires HTTPS in production and sometimes a user-gesture; falls back gracefully (the input is `readOnly` so the user can manually select + Cmd-C if the button silently fails).
- **TTL selector vs default** — operator picks at create time; an unfocused operator using the default (14 days) is fine since that's the backend's default cap-friendly choice.

## Migration plan

- No DB migration. Schema unchanged.
- `ProjectShareResponse` gains a field — additive, OpenAPI-compatible (orval client regenerates with the new field but old clients still work since they ignore the extra field).
- Existing pending shares created before this change have token-hash only; they're listed as before. New shares created after this change disclose the token once on response.

## Open questions

- **Q: Should the reveal panel let the operator copy a "shareable email body" too** (e.g. a pre-formatted subject/body for forwarding)? Tentative: no; the email already went out, this is just a backup link.
- **Q: Should the list show `shared_by` (which admin issued it)?** It's available on `ProjectShareItem`; v1 omits to keep the table tight. Add when there are multiple sharers (and hover the row to disambiguate).

## References

- Issue ganjasan/fastsaas#30.
- ADR-013 — `role:guest_viewer` bundle definition.
- UC-001 — Practitioner shares one project read-only with external client.
- `openspec/specs/multi-tenancy/spec.md` — already-shipped share/accept requirements (issue #3).
