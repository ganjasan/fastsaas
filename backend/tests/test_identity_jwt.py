"""RS256 JWT issuance and verification with kid rotation."""

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
from fastsaas.identity.auth import jwt as auth_jwt
from fastsaas.identity.auth.jwt import (
    ALGORITHM,
    TokenExpiredError,
    TokenInvalidError,
    TokenWrongTypeError,
    decode_access,
    decode_refresh,
    encode_access,
    encode_refresh,
    get_unverified_header,
    reload_keys,
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
    """Fresh per-test keypair; settings point at tmp_path; keys cache cleared."""
    _generate_keypair(tmp_path, "test-1")
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_signing_kid", "test-1")
    monkeypatch.setattr(settings, "jwt_signing_key_path", str(tmp_path / "test-1.pem"))
    monkeypatch.setattr(settings, "jwt_public_keys_dir", str(tmp_path))
    reload_keys()
    yield tmp_path
    reload_keys()


def _make_actor() -> Actor:
    return Actor(
        id=uuid_utils.uuid7(),
        actor_type=ActorType.HUMAN,
        display_name="Test",
        parent_actor_id=None,
    )


def test_access_token_roundtrip(jwt_keys: Path) -> None:
    """GIVEN an actor WHEN access token is signed and decoded THEN claims match."""
    actor = _make_actor()
    family = uuid4()
    token = encode_access(actor, family)
    claims = decode_access(token)
    assert claims["sub"] == str(actor.id)
    assert claims["actor_type"] == "HUMAN"
    assert claims["parent_actor_id"] is None
    assert claims["family_id"] == str(family)
    assert claims["type"] == "access"
    assert claims["exp"] - claims["iat"] == 900


def test_refresh_token_roundtrip(jwt_keys: Path) -> None:
    """GIVEN family + jti WHEN refresh token is signed and decoded THEN claims match."""
    actor = _make_actor()
    family = uuid4()
    jti = uuid4()
    token = encode_refresh(family, jti, actor.id)
    claims = decode_refresh(token)
    assert claims["family_id"] == str(family)
    assert claims["jti"] == str(jti)
    assert claims["sub"] == str(actor.id)
    assert claims["type"] == "refresh"
    assert claims["exp"] - claims["iat"] == 30 * 24 * 3600


def test_decoding_access_as_refresh_raises_wrong_type(jwt_keys: Path) -> None:
    """GIVEN an access token WHEN decoded as refresh THEN TokenWrongType raises."""
    token = encode_access(_make_actor(), uuid4())
    with pytest.raises(TokenWrongTypeError):
        decode_refresh(token)


def test_token_with_unknown_kid_raises_invalid(jwt_keys: Path) -> None:
    """GIVEN a token signed with an unknown kid WHEN decoded THEN TokenInvalid raises."""
    settings = get_settings()
    priv = RSAKey.import_key(Path(settings.jwt_signing_key_path).read_bytes())
    now = datetime.now(UTC)
    token = joserfc_jwt.encode(
        {"alg": ALGORITHM, "kid": "unknown"},
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "type": "access",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=15)).timestamp()),
        },
        priv,
    )
    with pytest.raises(TokenInvalidError, match="unknown kid"):
        decode_access(token)


def test_expired_token_raises_expired(jwt_keys: Path) -> None:
    """GIVEN a token whose exp is in the past WHEN decoded THEN TokenExpired raises."""
    settings = get_settings()
    priv = RSAKey.import_key(Path(settings.jwt_signing_key_path).read_bytes())
    past = datetime.now(UTC) - timedelta(minutes=1)
    token = joserfc_jwt.encode(
        {"alg": ALGORITHM, "kid": "test-1"},
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "type": "access",
            "iat": int((past - timedelta(seconds=1)).timestamp()),
            "exp": int(past.timestamp()),
        },
        priv,
    )
    with pytest.raises(TokenExpiredError):
        decode_access(token)


def test_token_signed_with_rotated_kid_still_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GIVEN an access token signed under previous kid WHEN both pub keys are present THEN it decodes."""
    # Issue a token under "test-1".
    _generate_keypair(tmp_path, "test-1")
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_signing_kid", "test-1")
    monkeypatch.setattr(settings, "jwt_signing_key_path", str(tmp_path / "test-1.pem"))
    monkeypatch.setattr(settings, "jwt_public_keys_dir", str(tmp_path))
    reload_keys()
    token = encode_access(_make_actor(), uuid4())

    # Rotate to "test-2" — keep "test-1" public key alongside.
    _generate_keypair(tmp_path, "test-2")
    monkeypatch.setattr(settings, "jwt_signing_kid", "test-2")
    monkeypatch.setattr(settings, "jwt_signing_key_path", str(tmp_path / "test-2.pem"))
    reload_keys()

    # Old token must still verify.
    claims = decode_access(token)
    assert claims["type"] == "access"

    # Newly issued token uses the new kid.
    new_token = encode_access(_make_actor(), uuid4())
    new_header = get_unverified_header(new_token)
    assert new_header["kid"] == "test-2"
    reload_keys()


def test_dev_keys_on_disk_are_loadable() -> None:
    """GIVEN the committed dev keypair WHEN imported by name THEN it round-trips a token."""
    repo_root = Path(__file__).resolve().parents[2]
    priv = repo_root / "infra/dev-secrets/jwt/dev-1.pem"
    pub = repo_root / "infra/dev-secrets/jwt/dev-1.pub.pem"
    assert priv.is_file(), f"missing committed dev signing key at {priv}"
    assert pub.is_file(), f"missing committed dev public key at {pub}"
    auth_jwt.reload_keys()  # ensure no leak from prior test
    # We don't override settings here — defaults already point at infra/dev-secrets/jwt.
    actor = _make_actor()
    token = encode_access(actor, uuid4())
    claims = decode_access(token)
    assert claims["sub"] == str(actor.id)
    auth_jwt.reload_keys()
