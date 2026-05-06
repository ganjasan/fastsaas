## ADDED Requirements

### Requirement: Project share-create response carries a one-time raw token

The system SHALL extend `ProjectShareResponse` (returned by `POST /orgs/{slug}/projects/{slug}/shares`) with a `raw_token: str` field carrying the freshly minted invite token. This is a one-time disclosure: the backend stores `sha256(token)` and never re-discloses it. The list endpoint (`GET .../shares` returning `ProjectShareItem`) SHALL NOT carry the field.

#### Scenario: Create response includes the email-delivered token

- **GIVEN** an owner shares project `alpha` with `guest@example.com`
- **WHEN** `POST /orgs/acme/projects/alpha/shares` returns 201
- **THEN** the response body contains `raw_token` equal to the token in the email-delivered invite link

#### Scenario: List response omits the raw token

- **GIVEN** a previously created share
- **WHEN** `GET /orgs/acme/projects/alpha/shares` returns 200
- **THEN** each list item contains `id`, `email`, `shared_by`, `expires_at`, `created_at`
- **AND** no item carries a `raw_token` field

### Requirement: Project page surfaces a sharing section for capable actors

The system SHALL render a `<ProjectSharing>` section on `/orgs/{slug}/projects/{projectSlug}` containing an "Invite a guest" form (email + TTL selector + Share button) and a "Pending invites" list with revoke actions. The form submits to the existing share endpoint; the list reads from the existing list endpoint; revoke calls the existing delete endpoint.

#### Scenario: Owner sees the sharing section

- **GIVEN** an owner of org `acme` opens project `alpha`
- **WHEN** the page renders
- **THEN** the Sharing section is visible with the invite form and the empty-state pending-invites list

#### Scenario: Successful share reveals copyable link once

- **GIVEN** the owner submits the form for `guest@example.com` with TTL 14 days
- **WHEN** the request returns 201
- **THEN** a reveal panel renders with a `readOnly` input containing `${origin}/orgs/accept-share/${raw_token}`
- **AND** a Copy button writes the link to the clipboard
- **AND** a Dismiss button removes the reveal panel
- **AND** an entry for `guest@example.com` appears in the pending-invites list

#### Scenario: Revoke invalidates the pending share

- **GIVEN** the operator clicks Revoke on a pending share for `guest@example.com`
- **WHEN** they confirm in the browser dialog
- **THEN** `DELETE /orgs/{slug}/projects/{slug}/shares/{share_id}` is issued
- **AND** the row disappears from the pending list on success

#### Scenario: Non-capable actor hits 403 on submit

- **GIVEN** a `role:viewer` actor (no `share:project` capability) opens the project page
- **WHEN** they submit the invite form
- **THEN** the request returns 403 `authz.forbidden`
- **AND** an error message appears under the form (UI does not pre-hide the section in v1; backend enforces)
