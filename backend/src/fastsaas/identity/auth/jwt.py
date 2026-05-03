"""RS256 JWT issuance + verification with rotatable kid.

Per ADR-008 §8a, ADR-018, and design.md §D1:
- Active signing key lives at `settings.jwt_signing_key_path` with id `jwt_signing_kid`.
- Verification keys live in `settings.jwt_public_keys_dir` as `<kid>.pub.pem` files.
- Tokens carry `kid` in their header so the verifier can pick the right public key.
- Two token types share the signing surface: access (15-min) and refresh (30-day).

Keys are read once and memoised; `reload_keys()` clears the cache (for tests + rotation).
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from uuid import UUID

from joserfc import jwt as _jwt
from joserfc.errors import ExpiredTokenError, JoseError
from joserfc.jwk import RSAKey
from joserfc.jwt import JWTClaimsRegistry

from fastsaas.config import get_settings
from fastsaas.identity.models import Actor

ALGORITHM = "RS256"
ACCESS_TTL = timedelta(minutes=15)
REFRESH_TTL = timedelta(days=30)
_CLAIMS_REGISTRY = JWTClaimsRegistry()


class TokenError(Exception):
    """Base for token decode failures."""

    code: str = "auth.token_invalid"


class TokenExpiredError(TokenError):
    code = "auth.token_expired"


class TokenInvalidError(TokenError):
    code = "auth.token_invalid"


class TokenWrongTypeError(TokenError):
    code = "auth.token_wrong_type"


@lru_cache
def _signing_key() -> RSAKey:
    pem = Path(get_settings().jwt_signing_key_path).read_bytes()
    return RSAKey.import_key(pem)


@lru_cache
def _verification_keys() -> dict[str, RSAKey]:
    """Map kid -> RSAKey. Reads every `<kid>.pub.pem` in jwt_public_keys_dir."""
    pubdir = Path(get_settings().jwt_public_keys_dir)
    if not pubdir.is_dir():
        return {}
    keys: dict[str, RSAKey] = {}
    for pub in pubdir.glob("*.pub.pem"):
        kid = pub.name.removesuffix(".pub.pem")
        keys[kid] = RSAKey.import_key(pub.read_bytes())
    return keys


def reload_keys() -> None:
    """Drop cached keys; next call re-reads from disk. Used in tests + rotation."""
    _signing_key.cache_clear()
    _verification_keys.cache_clear()


def get_unverified_header(token: str) -> dict:
    """Extract JWT header without verifying signature."""
    seg = token.split(".")[0]
    seg += "=" * (-len(seg) % 4)
    return json.loads(base64.urlsafe_b64decode(seg))


def encode_access(actor: Actor, family_id: UUID) -> str:
    """Sign an access JWT for `actor` bound to refresh `family_id`."""
    now = datetime.now(UTC)
    return _jwt.encode(
        {"alg": ALGORITHM, "kid": get_settings().jwt_signing_kid},
        {
            "sub": str(actor.id),
            # SQLModel returns actor_type as a raw str (storage is `Column(String)`); StrEnum's str() yields its value.
            "actor_type": str(actor.actor_type),
            "parent_actor_id": str(actor.parent_actor_id) if actor.parent_actor_id else None,
            "family_id": str(family_id),
            "iat": int(now.timestamp()),
            "exp": int((now + ACCESS_TTL).timestamp()),
            "type": "access",
        },
        _signing_key(),
    )


def encode_refresh(family_id: UUID, jti: UUID, user_actor_id: UUID) -> str:
    """Sign a refresh JWT for the given family + jti."""
    now = datetime.now(UTC)
    return _jwt.encode(
        {"alg": ALGORITHM, "kid": get_settings().jwt_signing_kid},
        {
            "sub": str(user_actor_id),
            "family_id": str(family_id),
            "jti": str(jti),
            "iat": int(now.timestamp()),
            "exp": int((now + REFRESH_TTL).timestamp()),
            "type": "refresh",
        },
        _signing_key(),
    )


def decode_with_type(token: str, expected_type: str) -> dict:
    """Verify signature/exp + assert `type` claim equals `expected_type`. Raises Token* errors."""
    try:
        header = get_unverified_header(token)
    except Exception as e:
        raise TokenInvalidError(str(e)) from e
    kid = header.get("kid")
    if not kid:
        raise TokenInvalidError("token has no kid")
    pubkey = _verification_keys().get(kid)
    if not pubkey:
        raise TokenInvalidError(f"unknown kid: {kid}")
    try:
        decoded = _jwt.decode(token, pubkey, algorithms=[ALGORITHM])
        _CLAIMS_REGISTRY.validate(decoded.claims)
    except ExpiredTokenError as e:
        raise TokenExpiredError(str(e)) from e
    except JoseError as e:
        raise TokenInvalidError(str(e)) from e
    claims = decoded.claims
    if claims.get("type") != expected_type:
        raise TokenWrongTypeError(f"expected {expected_type}, got {claims.get('type')}")
    return dict(claims)


def sign_with_active_key(claims: dict) -> str:
    """Sign `claims` with the active kid + RS256. Caller is responsible for iat/exp/type."""
    return _jwt.encode(
        {"alg": ALGORITHM, "kid": get_settings().jwt_signing_kid},
        claims,
        _signing_key(),
    )


def decode_access(token: str) -> dict:
    """Verify and decode an access JWT; raises TokenExpired/Invalid/WrongType."""
    return decode_with_type(token, "access")


def decode_refresh(token: str) -> dict:
    """Verify and decode a refresh JWT; raises TokenExpired/Invalid/WrongType."""
    return decode_with_type(token, "refresh")
