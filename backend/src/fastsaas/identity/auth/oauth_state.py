"""OAuth state token — short-lived JWT carried through the redirect dance.

The state token guards against CSRF and stitches the OIDC nonce + post-login
redirect together. It is signed with the same RS256 keypair as access/refresh
tokens (per ADR-008 §8a) but uses a distinct `type` claim so it cannot be
swapped for an access or refresh token.

Lifetime: 5 minutes — long enough for the user to complete the consent screen,
short enough that a leaked state cannot be replayed at leisure.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from fastsaas.identity.auth.jwt import decode_with_type, sign_with_active_key

STATE_TTL = timedelta(minutes=5)
_STATE_TYPE = "oauth_state"


def generate_nonce() -> str:
    """Cryptographically random nonce for the OIDC `nonce` parameter."""
    return secrets.token_urlsafe(24)


def mint_state(*, provider: str, redirect_to: str, nonce: str) -> str:
    """Sign a state JWT carrying provider + post-login redirect + OIDC nonce."""
    now = datetime.now(UTC)
    return sign_with_active_key(
        {
            "provider": provider,
            "redirect_to": redirect_to,
            "nonce": nonce,
            "iat": int(now.timestamp()),
            "exp": int((now + STATE_TTL).timestamp()),
            "type": _STATE_TYPE,
        }
    )


def verify_state(token: str) -> dict:
    """Verify the state JWT and return its claims; raises Token{Expired,Invalid,WrongType}."""
    return decode_with_type(token, _STATE_TYPE)
