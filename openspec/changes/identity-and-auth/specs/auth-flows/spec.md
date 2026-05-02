## ADDED Requirements

### Requirement: Email-and-password registration with mandatory verification

The system SHALL allow a prospective user to register with email and password, persist a HUMAN actor with `email_verified = FALSE`, and email a single-use verification magic-link with a 24-hour TTL per ADR-008 §8c.

#### Scenario: Successful registration sends verification email

- **WHEN** a request `POST /auth/register` carries a valid email and a password meeting policy
- **THEN** the system creates `actors` and `users` rows in one transaction
- **AND** the response is HTTP 201 with the new actor's id and `email_verified: false`
- **AND** an email is delivered to Mailhog containing a URL of the form `<APP_URL>/auth/verify-email/<token>`
- **AND** a row exists in `magic_link_tokens` with `purpose = 'email_verification'` and `expires_at` 24 hours in the future

#### Scenario: Duplicate email is rejected

- **WHEN** a registration request uses an email already present in `users`
- **THEN** the response is HTTP 409 with code `auth.email_taken`
- **AND** no new rows are inserted

#### Scenario: Weak password is rejected

- **WHEN** a registration request submits a password under 12 characters
- **THEN** the response is HTTP 400 with code `auth.password_too_short`

### Requirement: Email verification

The system SHALL flip `users.email_verified` to TRUE when a user consumes a valid verification magic-link, mark the token consumed atomically, and reject reuse.

#### Scenario: Valid token verifies email

- **WHEN** `POST /auth/verify-email` is called with the raw token from a non-expired non-consumed `email_verification` row
- **THEN** the same transaction sets `users.email_verified = TRUE` and `magic_link_tokens.consumed_at = NOW()`
- **AND** the response is HTTP 200

#### Scenario: Expired token is rejected

- **WHEN** the token's `expires_at` is in the past
- **THEN** the response is HTTP 410 with code `auth.token_expired`
- **AND** `users.email_verified` is NOT changed

#### Scenario: Already-consumed token is rejected

- **WHEN** the token row has `consumed_at IS NOT NULL`
- **THEN** the response is HTTP 410 with code `auth.token_consumed`

### Requirement: Email-and-password login

The system SHALL authenticate a user by verifying their password against the stored Argon2id hash, refusing login when email is unverified, and issuing access + refresh tokens on success per ADR-008.

#### Scenario: Successful login with verified email

- **WHEN** `POST /auth/login` receives correct credentials for a user with `email_verified = TRUE`
- **THEN** the response is HTTP 200 with body containing the access token and `expires_in: 900`
- **AND** the response sets a refresh cookie (httpOnly, Secure, SameSite=Lax, Path=/auth)
- **AND** a Redis hash exists at `refresh:fam:<family_id>` with `current_jti`, `user_actor_id`, `expires_at`

#### Scenario: Login refused for unverified email

- **WHEN** `POST /auth/login` receives correct credentials for a user with `email_verified = FALSE`
- **THEN** the response is HTTP 403 with code `auth.email_unverified`
- **AND** no tokens are issued

#### Scenario: Wrong password returns generic 401

- **WHEN** `POST /auth/login` receives a wrong password
- **THEN** the response is HTTP 401 with code `auth.invalid_credentials`
- **AND** the error message does NOT distinguish between "no such user" and "wrong password"

### Requirement: Logout revokes refresh family

The system SHALL invalidate the refresh-token family on logout so that the refresh cookie cannot be replayed.

#### Scenario: Logout deletes Redis family record

- **WHEN** `POST /auth/logout` is called with the refresh cookie present
- **THEN** the server deletes the corresponding `refresh:fam:<family_id>` Redis key
- **AND** the response clears the refresh cookie via `Set-Cookie: <name>=; Max-Age=0; Path=/auth`

### Requirement: Magic-link login

The system SHALL allow a user to request a magic-link login email and consume it within 15 minutes per ADR-008 §8c, issuing a fresh refresh family on success.

#### Scenario: Magic-link request emails a one-time URL

- **WHEN** `POST /auth/magic-link/request` is called with an email matching a verified user
- **THEN** an email is delivered to Mailhog containing `<APP_URL>/auth/magic-link/<token>`
- **AND** a row exists in `magic_link_tokens` with `purpose = 'magic_link_login'` and 15-minute `expires_at`
- **AND** the response is HTTP 202 regardless of whether the email exists, to prevent enumeration

#### Scenario: Consuming a magic-link issues tokens

- **WHEN** `POST /auth/magic-link/consume` is called with a valid token
- **THEN** the same transaction sets `magic_link_tokens.consumed_at = NOW()`
- **AND** the response issues access + refresh tokens identical in shape to a password login

### Requirement: Password reset

The system SHALL allow a user to request a password reset and complete it via single-use magic-link with 1-hour TTL per ADR-008 §8c.

#### Scenario: Reset request emails a token

- **WHEN** `POST /auth/password-reset/request` is called with an email
- **THEN** an email is delivered to Mailhog with `<APP_URL>/auth/reset-password/<token>` if the email matches a user
- **AND** the response is HTTP 202 regardless of email existence

#### Scenario: Consuming a reset token updates the password

- **WHEN** `POST /auth/password-reset/consume` is called with a valid token and a new compliant password
- **THEN** `users.password_hash` is updated with a new Argon2id hash in the same transaction as `consumed_at`
- **AND** all existing refresh families for this actor are deleted from Redis
- **AND** the response is HTTP 200

### Requirement: OAuth login — Google + Microsoft

The system SHALL support OAuth login via Google and Microsoft per ADR-008 §8d, creating a HUMAN actor with `email_verified = TRUE` on first login or linking to an existing email-matched user with explicit conflict handling.

#### Scenario: First-time OAuth creates a new user

- **WHEN** the OAuth callback returns identity for an email NOT in `users`
- **THEN** the system creates `actors`, `users` (with `email_verified = TRUE`), and `oauth_identities` in one transaction
- **AND** the system issues access + refresh tokens

#### Scenario: OAuth identity already linked logs the user in

- **WHEN** the OAuth callback returns identity matching an existing `oauth_identities` row
- **THEN** the system issues access + refresh tokens for the linked user

#### Scenario: OAuth email collides with a password-only user

- **WHEN** the OAuth callback returns identity whose email matches a user with no `oauth_identities` row for the provider
- **THEN** the response is HTTP 409 with code `auth.oauth_email_taken`
- **AND** the message instructs the user to sign in with password and link OAuth from settings

#### Scenario: OAuth dev bypass is configurable

- **WHEN** the env var `OAUTH_DEV_BYPASS=true` is set
- **AND** the request hits `/auth/oauth/dev/start` with `?email=<email>`
- **THEN** the callback completes immediately as if the provider returned that email
- **AND** with `OAUTH_DEV_BYPASS` unset or false, that endpoint returns HTTP 404

### Requirement: Frontend auth pages

The frontend SHALL expose a complete set of auth pages under `/auth/*` rendered by TanStack Router. Forms SHALL use React Hook Form + Zod for validation per ADR-004.

#### Scenario: Login page exists and posts to backend

- **WHEN** a user navigates to `/auth/login`
- **THEN** a form with email and password fields is rendered
- **AND** submitting valid input issues `POST /auth/login` and stores the access token in the in-memory `authStore`

#### Scenario: 401 from any API call triggers single refresh-and-retry

- **WHEN** an authenticated API call returns 401 with code `auth.token_expired`
- **THEN** the orval mutator calls `POST /auth/refresh` once with `X-Refresh: 1`
- **AND** retries the original request once with the new access token
- **AND** if the refresh itself fails, the user is redirected to `/auth/login`

#### Scenario: Concurrent 401s share one refresh in flight

- **WHEN** multiple API calls return 401 within the same tick
- **THEN** only one `POST /auth/refresh` is issued
- **AND** all original requests retry once after that single refresh resolves
