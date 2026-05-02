## ADDED Requirements

### Requirement: Access token shape and lifetime

The system SHALL issue access tokens as JWTs signed with RS256, valid for 15 minutes per ADR-008 §8a, carrying claims `sub` (actor id), `actor_type`, `parent_actor_id`, `kid` (key id), `family_id`, `iat`, and `exp`.

#### Scenario: Issued token decodes to expected claims

- **WHEN** a successful login returns an access token
- **THEN** decoding it with the active public key yields `sub` matching the actor id, `actor_type = 'HUMAN'`, `parent_actor_id = null`, and `exp - iat == 900`

#### Scenario: Tokens signed with rotated keys still verify

- **WHEN** an active access token was signed with a previous `kid` whose public key remains in `JWT_PUBLIC_KEYS_JSON`
- **THEN** verification succeeds until the token's natural expiry
- **AND** new tokens are signed with the current `JWT_SIGNING_KID`

### Requirement: Refresh tokens with rotation and reuse detection

The system SHALL implement rotating refresh tokens with reuse detection per ADR-008 §8a, storing per-family state in Redis keyed by `refresh:fam:<family_id>`.

#### Scenario: Successful refresh rotates the token

- **WHEN** `POST /auth/refresh` is called with a valid refresh cookie carrying current `jti`
- **THEN** the response sets a new refresh cookie with a new `jti` and a fresh 30-day expiry
- **AND** the response body returns a fresh access token
- **AND** the Redis hash `refresh:fam:<family_id>` is updated with the new `current_jti`

#### Scenario: Reusing an old refresh blacklists the family

- **WHEN** `POST /auth/refresh` is called with a `jti` that is NOT the family's `current_jti`
- **THEN** the Redis key `refresh:fam:<family_id>` is deleted
- **AND** the response is HTTP 401 with code `auth.refresh_reused`
- **AND** all subsequent refreshes from any cookie in this family fail until re-login

#### Scenario: Refresh requires custom CSRF header

- **WHEN** `POST /auth/refresh` is called without `X-Refresh: 1` header
- **THEN** the response is HTTP 400 with code `auth.refresh_missing_header`
- **AND** the refresh cookie is NOT consumed

#### Scenario: Concurrent refreshes resolve to one rotation

- **WHEN** two concurrent `POST /auth/refresh` calls arrive with the same current `jti`
- **THEN** exactly one rotates and the other returns HTTP 401 `auth.refresh_reused`
  *— or the chosen implementation makes one wait and succeed, but never both rotate*
- **AND** Redis state is consistent (one `current_jti` after both calls return)

### Requirement: Token storage on the wire

The system SHALL deliver access tokens in JSON response bodies and refresh tokens only in httpOnly cookies per ADR-008 §8b.

#### Scenario: Refresh cookie attributes match policy

- **WHEN** any successful auth flow returns a refresh cookie
- **THEN** the `Set-Cookie` header includes `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/auth`
- **AND** the `Max-Age` is 2592000 (30 days)

#### Scenario: Access token is not returned via Set-Cookie

- **WHEN** any successful auth flow completes
- **THEN** no `Set-Cookie` header carries the access token

### Requirement: Magic-link tokens are single-use and hashed at rest

The system SHALL store magic-link tokens as `sha256(token)` and consume them in the same transaction as their side effect.

#### Scenario: Raw token never appears in storage

- **WHEN** any magic-link is generated
- **THEN** the value persisted in `magic_link_tokens.token_hash` is the SHA-256 hex digest of the raw token
- **AND** the raw token only appears in the outbound email body

#### Scenario: Consumption is atomic with side effect

- **WHEN** consuming a magic-link of any purpose
- **THEN** the database transaction sets `consumed_at` and applies the side effect (email-verified flip, password update, login completion) together
- **AND** rollback of either part rolls back the consumption

### Requirement: Logout cleanup

The system SHALL invalidate session state on logout in a way that prevents replay.

#### Scenario: Logout removes the refresh family

- **WHEN** `POST /auth/logout` is called with a valid refresh cookie
- **THEN** the corresponding `refresh:fam:<family_id>` Redis key is deleted
- **AND** the response clears the refresh cookie

#### Scenario: Access token continues to work until natural expiry

- **WHEN** a user logs out
- **AND** they reuse their previously-issued access token within its 15-minute lifetime
- **THEN** that access token still authenticates requests (acceptable per ADR-008)
- **AND** they cannot mint a new one — the next refresh attempt fails

### Requirement: Password reset invalidates all sessions

The system SHALL terminate all active refresh families for an actor when their password is reset.

#### Scenario: Reset wipes refresh families

- **WHEN** a password reset is consumed for an actor
- **THEN** every `refresh:fam:*` Redis key whose `user_actor_id` matches the actor is deleted
- **AND** any subsequent refresh attempt for that actor fails with `auth.refresh_reused` or `auth.refresh_unknown`
