---
title: Project share-link UI — owner issues guest access from project page
status: in_progress
linked_issue: ganjasan/fastsaas#30
created: 2026-05-06
traces_to:
  adr:
    - "[[ADR-013_authorization-capabilities-role-bundles]]"
    - "[[ADR-007_multi-tenant-isolation]]"
  use_cases:
    - "UC-001 (per-project guest)"
  stakeholders: []
---

## Why

Per-project guest sharing (UC-001) has shipped end-to-end on the backend since #3:

- `POST /orgs/{slug}/projects/{slug}/shares` mints a one-time token, emails the recipient, returns the share record.
- `GET /orgs/{slug}/projects/{slug}/shares` lists pending shares.
- `DELETE /orgs/{slug}/projects/{slug}/shares/{id}` revokes.
- Recipient flow lives at `/orgs/accept-share/{token}` (frontend already shipped).

What's missing: the **owner-side UI to issue a share**. Until this lands, operators must drive the API by curl. The feature is essentially undiscoverable.

## What changes

1. **Backend `ProjectShareResponse` adds `raw_token: str`** — one-time disclosure on the create endpoint so the operator UI can show a copyable invite link without digging through the recipient's mailbox. The list endpoint (`ProjectShareItem`) deliberately omits the token; backend stores `sha256(token)` so re-display is impossible after navigation away.
2. **`<ProjectSharing>` component** rendered in `routes/orgs/$slug.projects.$projectSlug.tsx`:
   - "Invite a guest" form: email + TTL select (3 / 7 / 14 / 30 days) + Share button.
   - On success: copyable input with the link `${origin}/orgs/accept-share/${raw_token}` + "Copy" button + "Dismiss" action. The raw token is shown ONCE; we surface the email-delivered same-link copy so the inviting admin can paste it into a private channel without waiting for the recipient.
   - "Pending invites" card: list of email / expires_at / Revoke per row.
3. **Capability gate** — the form + list rely on the existing backend `share:project` gate. Members and viewers without the capability get 403 from the API; the UI surfaces the section anyway today and the API enforces. Hiding the section client-side is a polish follow-up that depends on a `useCan` hook (not in v1).

## What does NOT change

- The recipient flow (`/orgs/accept-share/{token}`) is untouched.
- The token-hash storage / revocation semantics on the backend.
- The capability gate (`share:project` for owner/admin) — same gate as before.
- The org-invitation UI is unchanged. The two flows stay distinct.

## Out of scope

- Editing an existing share (e.g. extending TTL). Revoke + re-issue covers v1.
- Bulk share — single-use is intentional per UC-001.
- Granting more than `read` to a guest. Lands when #31 (per-project member access) ships.
- A `useCan` hook to hide the section client-side for non-owners. Backend already enforces 403; UI hint is a follow-up.
