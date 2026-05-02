---
id: ADR-018
title: JWT and OAuth library — Authlib instead of python-jose + httpx-oauth
status: accepted
created: 2026-05-01
traces_to:
  - ADR-008
  - openspec/changes/identity-and-auth
---

# ADR-018: Authlib as the single JWT + OAuth library

## Context

The identity layer (ADR-008) requires:
- RS256 JWT issuance and verification (access + refresh tokens, OAuth state tokens)
- OAuth 2.0 / OIDC flows for Google and Microsoft (PKCE, discovery, id_token validation)

Two candidate stacks were evaluated:

| Concern | python-jose + httpx-oauth | authlib |
|---|---|---|
| OIDC discovery (`.well-known`) | manual fetch | built-in `AsyncOAuth2Client.load_server_metadata()` |
| id_token validation (sig/iss/aud/exp/nonce) | manual | built-in `parse_id_token()` |
| JWKS rotation / caching | manual | built-in |
| PKCE | manual | built-in |
| RFC 9700 / OWASP compliance | ~300-400 LOC to reach parity | ~80-100 LOC |
| Maintenance | python-jose unmaintained since 2023 | actively maintained |
| JWT API surface | `jwt.encode/decode` | `JsonWebToken().encode/decode` |

## Decision

Use the **Authlib + joserfc** stack as the sole JWT + OAuth surface, replacing both `python-jose[cryptography]` and `httpx-oauth`.

- JWT: `joserfc>=1.0` (the JOSE library Authlib itself migrated to; `authlib.jose` is deprecated as of authlib 1.7)
- OAuth/OIDC: `authlib.integrations.httpx_client.AsyncOAuth2Client`

`joserfc` is a focused JOSE/JWT package; `authlib` is kept for its OAuth client integration.

## Consequences

- `pyproject.toml`: remove `python-jose[cryptography]` and `httpx-oauth`; add `authlib>=1.3` and `joserfc>=1.0`
- `auth/jwt.py`: rewrite encoding/decoding to use `joserfc.jwt` + `joserfc.jwk.RSAKey`; same caller-facing API (`encode_access`, `decode_access`, …) preserved
- `auth/oauth.py`: implement using `AsyncOAuth2Client` with OIDC discovery (Phase 8)
- All 43 existing tests stay green after the jwt.py rewrite
