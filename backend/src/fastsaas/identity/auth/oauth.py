"""OAuth/OIDC providers — Google + Microsoft.

Per ADR-018 and design.md §D4: Authlib's `AsyncOAuth2Client` runs the OAuth2 +
PKCE dance; OIDC discovery and JWKS validation are layered on top with `joserfc`
so we meet RFC 9700 / OWASP guidance (sig + iss + aud + exp + nonce on
id_token) without hand-rolling JOSE primitives.

Discovery + JWKS docs are cached in-process; call `clear_cache()` before
retrying after a JWKS-key-rotation event.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from joserfc import jwt as _jwt
from joserfc.errors import JoseError
from joserfc.jwk import KeySet

from fastsaas.config import get_settings
from fastsaas.identity.auth.oauth_state import (
    generate_nonce,
    mint_state,
    verify_state,
)

logger = logging.getLogger(__name__)


class OAuthError(Exception):
    """Base for OAuth-flow failures."""

    code: str = "auth.oauth_failed"


class OAuthStateInvalidError(OAuthError):
    code = "auth.oauth_state_invalid"


class OAuthIdTokenInvalidError(OAuthError):
    code = "auth.oauth_id_token_invalid"


class OAuthDiscoveryError(OAuthError):
    code = "auth.oauth_discovery_failed"


@dataclass(frozen=True)
class OAuthIdentityClaims:
    """Result of a successful OAuth callback — what we need to look up / create a User."""

    provider: str
    provider_uid: str
    email: str
    email_verified: bool
    redirect_to: str


@dataclass
class OIDCProvider:
    """One OIDC-compliant identity provider (Google, Microsoft, ...).

    `discovery_url` resolves to the issuer's `.well-known/openid-configuration`
    document; everything else (authorize endpoint, token endpoint, JWKS URI,
    expected `iss`) is discovered.

    `provider_uid_fn` extracts the stable user id from the id_token claims —
    Google: `sub`; Microsoft: `<tid>:<oid>` so a tenant move doesn't collide.
    """

    name: str
    discovery_url: str
    client_id: str
    client_secret: str
    scopes: tuple[str, ...] = ("openid", "email", "profile")
    provider_uid_fn: Callable[[dict], str] = field(default=lambda c: c["sub"])

    async def start(
        self, *, redirect_uri: str, redirect_to: str
    ) -> tuple[str, str, str]:
        """Build the authorize URL + sign the state JWT.

        Returns `(authorize_url, state_token, code_verifier)`. The caller stores
        `code_verifier` (e.g. in an HttpOnly cookie) and presents it back during
        the callback to complete the PKCE exchange.
        """
        meta = await _fetch_metadata(self.discovery_url)
        nonce = generate_nonce()
        state_token = mint_state(
            provider=self.name, redirect_to=redirect_to, nonce=nonce
        )
        code_verifier = secrets.token_urlsafe(64)
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope=" ".join(self.scopes),
            redirect_uri=redirect_uri,
        ) as client:
            url, _ = client.create_authorization_url(
                meta["authorization_endpoint"],
                state=state_token,
                code_challenge=_pkce_challenge(code_verifier),
                code_challenge_method="S256",
                nonce=nonce,
            )
        return url, state_token, code_verifier

    async def complete(
        self,
        *,
        code: str,
        state_token: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> OAuthIdentityClaims:
        """Verify state, exchange code for tokens, validate id_token, return claims."""
        try:
            state_claims = verify_state(state_token)
        except Exception as e:
            raise OAuthStateInvalidError(str(e)) from e
        if state_claims.get("provider") != self.name:
            raise OAuthStateInvalidError(
                f"state was for provider {state_claims.get('provider')}, not {self.name}"
            )

        meta = await _fetch_metadata(self.discovery_url)
        async with AsyncOAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope=" ".join(self.scopes),
            redirect_uri=redirect_uri,
        ) as client:
            token = await client.fetch_token(
                meta["token_endpoint"],
                code=code,
                code_verifier=code_verifier,
                grant_type="authorization_code",
            )

        id_token = token.get("id_token")
        if not id_token:
            raise OAuthIdTokenInvalidError("no id_token in token response")

        claims = await self._validate_id_token(
            id_token,
            expected_iss=meta["issuer"],
            expected_nonce=state_claims["nonce"],
            jwks_uri=meta["jwks_uri"],
        )

        email = claims.get("email")
        if not email:
            raise OAuthIdTokenInvalidError("id_token missing email claim")

        return OAuthIdentityClaims(
            provider=self.name,
            provider_uid=self.provider_uid_fn(claims),
            email=email,
            email_verified=bool(claims.get("email_verified", False)),
            redirect_to=state_claims.get("redirect_to", "/"),
        )

    async def _validate_id_token(
        self,
        id_token: str,
        *,
        expected_iss: str,
        expected_nonce: str,
        jwks_uri: str,
    ) -> dict:
        jwks = await _fetch_jwks(jwks_uri)
        try:
            decoded = _jwt.decode(id_token, jwks)
        except JoseError as e:
            raise OAuthIdTokenInvalidError(f"id_token signature invalid: {e}") from e

        claims = dict(decoded.claims)
        now = int(datetime.now(UTC).timestamp())

        if claims.get("iss") != expected_iss and not _microsoft_issuer_matches(
            expected_iss, claims.get("iss", "")
        ):
            raise OAuthIdTokenInvalidError(
                f"id_token iss {claims.get('iss')!r} != expected {expected_iss!r}"
            )

        aud = claims.get("aud")
        if aud != self.client_id and self.client_id not in (aud if isinstance(aud, list) else []):
            raise OAuthIdTokenInvalidError("id_token aud != our client_id")

        if not claims.get("exp") or claims["exp"] <= now:
            raise OAuthIdTokenInvalidError("id_token expired")

        if claims.get("nonce") != expected_nonce:
            raise OAuthIdTokenInvalidError("id_token nonce mismatch")

        return claims


def _pkce_challenge(verifier: str) -> str:
    """Compute the S256 PKCE code_challenge from a code_verifier (RFC 7636)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _microsoft_issuer_matches(expected: str, actual: str) -> bool:
    """Microsoft's `common` endpoint discovers iss as a literal `{tenantid}` placeholder."""
    if "{tenantid}" not in expected:
        return False
    head, tail = expected.split("{tenantid}", 1)
    return actual.startswith(head) and actual.endswith(tail)


_metadata_cache: dict[str, dict] = {}
_jwks_cache: dict[str, KeySet] = {}


async def _fetch_metadata(discovery_url: str) -> dict:
    if discovery_url in _metadata_cache:
        return _metadata_cache[discovery_url]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(discovery_url)
            resp.raise_for_status()
            meta = resp.json()
    except httpx.HTTPError as e:
        raise OAuthDiscoveryError(f"failed to fetch {discovery_url}: {e}") from e
    _metadata_cache[discovery_url] = meta
    return meta


async def _fetch_jwks(jwks_uri: str) -> KeySet:
    if jwks_uri in _jwks_cache:
        return _jwks_cache[jwks_uri]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(jwks_uri)
            resp.raise_for_status()
            jwks = resp.json()
    except httpx.HTTPError as e:
        raise OAuthDiscoveryError(f"failed to fetch {jwks_uri}: {e}") from e
    keyset = KeySet.import_key_set(jwks)
    _jwks_cache[jwks_uri] = keyset
    return keyset


def clear_cache() -> None:
    """Drop discovery + JWKS caches; next call re-fetches. Useful for tests + key rotation."""
    _metadata_cache.clear()
    _jwks_cache.clear()


def google_provider() -> OIDCProvider:
    s = get_settings()
    return OIDCProvider(
        name="google",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=s.oauth_google_client_id,
        client_secret=s.oauth_google_client_secret,
    )


def microsoft_provider() -> OIDCProvider:
    s = get_settings()
    return OIDCProvider(
        name="microsoft",
        discovery_url=(
            f"https://login.microsoftonline.com/{s.oauth_microsoft_tenant}"
            "/v2.0/.well-known/openid-configuration"
        ),
        client_id=s.oauth_microsoft_client_id,
        client_secret=s.oauth_microsoft_client_secret,
        provider_uid_fn=_microsoft_provider_uid,
    )


def _microsoft_provider_uid(claims: dict) -> str:
    tid = claims.get("tid", "")
    oid = claims.get("oid") or claims.get("sub", "")
    return f"{tid}:{oid}"
