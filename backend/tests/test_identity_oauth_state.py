"""OAuth state JWT — mint, verify, expiry, wrong type, nonce uniqueness."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import uuid_utils
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import RSAKey

from fastsaas.config import get_settings
from fastsaas.identity.auth.jwt import (
    ALGORITHM,
    TokenExpiredError,
    TokenInvalidError,
    TokenWrongTypeError,
    encode_access,
    reload_keys,
)
from fastsaas.identity.auth.oauth_state import (
    STATE_TTL,
    generate_nonce,
    mint_state,
    verify_state,
)
from fastsaas.identity.models import Actor, ActorType


def _generate_keypair(tmp_path: Path, kid: str) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path = tmp_path / f"{kid}.pem"
    pub_path = tmp_path / f"{kid}.pub.pem"
    priv_path.write_bytes(priv_pem)
    pub_path.write_bytes(pub_pem)
    return priv_path, pub_path


@pytest.fixture
def jwt_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    _generate_keypair(tmp_path, "test-1")
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_signing_kid", "test-1")
    monkeypatch.setattr(settings, "jwt_signing_key_path", str(tmp_path / "test-1.pem"))
    monkeypatch.setattr(settings, "jwt_public_keys_dir", str(tmp_path))
    reload_keys()
    yield tmp_path
    reload_keys()


def test_state_round_trip(jwt_keys: Path) -> None:
    """GIVEN provider + redirect + nonce WHEN minted and verified THEN claims match."""
    nonce = generate_nonce()
    token = mint_state(provider="google", redirect_to="/dashboard", nonce=nonce)

    claims = verify_state(token)

    assert claims["provider"] == "google"
    assert claims["redirect_to"] == "/dashboard"
    assert claims["nonce"] == nonce
    assert claims["type"] == "oauth_state"
    assert claims["exp"] - claims["iat"] == int(STATE_TTL.total_seconds())


def test_verify_state_rejects_access_token(jwt_keys: Path) -> None:
    """GIVEN an access JWT WHEN verified as state THEN TokenWrongType raises."""
    actor = Actor(id=uuid_utils.uuid7(), actor_type=ActorType.HUMAN, display_name="X")
    access = encode_access(actor, uuid4())

    with pytest.raises(TokenWrongTypeError):
        verify_state(access)


def test_verify_state_rejects_expired(jwt_keys: Path) -> None:
    """GIVEN a state token whose exp is in the past WHEN verified THEN TokenExpired raises."""
    settings = get_settings()
    priv = RSAKey.import_key(Path(settings.jwt_signing_key_path).read_bytes())
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = joserfc_jwt.encode(
        {"alg": ALGORITHM, "kid": "test-1"},
        {
            "provider": "google",
            "redirect_to": "/",
            "nonce": "n",
            "type": "oauth_state",
            "iat": int((past - timedelta(seconds=1)).timestamp()),
            "exp": int(past.timestamp()),
        },
        priv,
    )

    with pytest.raises(TokenExpiredError):
        verify_state(token)


def test_verify_state_rejects_unknown_kid(jwt_keys: Path) -> None:
    """GIVEN a state-shaped token signed under an unknown kid WHEN verified THEN TokenInvalid raises."""
    settings = get_settings()
    priv = RSAKey.import_key(Path(settings.jwt_signing_key_path).read_bytes())
    now = datetime.now(UTC)
    token = joserfc_jwt.encode(
        {"alg": ALGORITHM, "kid": "ghost"},
        {
            "provider": "google",
            "redirect_to": "/",
            "nonce": "n",
            "type": "oauth_state",
            "iat": int(now.timestamp()),
            "exp": int((now + STATE_TTL).timestamp()),
        },
        priv,
    )

    with pytest.raises(TokenInvalidError, match="unknown kid"):
        verify_state(token)


def test_generate_nonce_is_unique() -> None:
    """GIVEN repeated calls THEN every nonce differs."""
    nonces = {generate_nonce() for _ in range(20)}
    assert len(nonces) == 20
    assert all(len(n) > 20 for n in nonces)
