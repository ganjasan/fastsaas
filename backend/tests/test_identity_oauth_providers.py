"""OAuth provider tests — Google + Microsoft, with mocked discovery + JWKS + token exchange.

These are unit tests: no real network. The module-level discovery + JWKS caches
are populated by the `mock_discovery` fixture; `AsyncOAuth2Client.fetch_token`
is monkeypatched to return a synthetic id_token signed with a test keypair.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from authlib.integrations.httpx_client import AsyncOAuth2Client
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from joserfc import jwt as joserfc_jwt
from joserfc.jwk import KeySet, RSAKey

from fastsaas.config import get_settings
from fastsaas.identity.auth import oauth as oauth_module
from fastsaas.identity.auth.jwt import reload_keys
from fastsaas.identity.auth.oauth import (
    OAuthIdentityClaims,
    OAuthIdTokenInvalidError,
    OAuthStateInvalidError,
    OIDCProvider,
    clear_cache,
    google_provider,
    microsoft_provider,
)
from fastsaas.identity.auth.oauth_state import generate_nonce, mint_state

GOOGLE_DISCOVERY = "https://accounts.google.com/.well-known/openid-configuration"
MOCK_ISSUER = "https://accounts.example.test"
MOCK_JWKS_URI = "https://accounts.example.test/jwks"
MOCK_AUTHZ = "https://accounts.example.test/authorize"
MOCK_TOKEN = "https://accounts.example.test/token"


def _generate_signing_keypair(tmp_path: Path, kid: str) -> None:
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
    (tmp_path / f"{kid}.pem").write_bytes(priv_pem)
    (tmp_path / f"{kid}.pub.pem").write_bytes(pub_pem)


@pytest.fixture
def jwt_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Per-test RS256 keypair used by mint_state / verify_state."""
    _generate_signing_keypair(tmp_path, "test-1")
    settings = get_settings()
    monkeypatch.setattr(settings, "jwt_signing_kid", "test-1")
    monkeypatch.setattr(settings, "jwt_signing_key_path", str(tmp_path / "test-1.pem"))
    monkeypatch.setattr(settings, "jwt_public_keys_dir", str(tmp_path))
    reload_keys()
    yield tmp_path
    reload_keys()


@pytest.fixture
def provider_keypair() -> tuple[RSAKey, KeySet]:
    """Mock provider's signing keypair — used to forge id_tokens."""
    raw = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_pem = raw.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = raw.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_key = RSAKey.import_key(priv_pem, parameters={"kid": "provider-1"})
    pub_key = RSAKey.import_key(pub_pem, parameters={"kid": "provider-1"})
    keyset = KeySet([pub_key])
    return priv_key, keyset


@pytest.fixture
def mock_discovery(
    monkeypatch: pytest.MonkeyPatch, provider_keypair: tuple[RSAKey, KeySet]
) -> Iterator[None]:
    """Patch _fetch_metadata + _fetch_jwks so providers hit no real network."""
    _, keyset = provider_keypair
    metadata = {
        "issuer": MOCK_ISSUER,
        "authorization_endpoint": MOCK_AUTHZ,
        "token_endpoint": MOCK_TOKEN,
        "jwks_uri": MOCK_JWKS_URI,
    }

    async def fake_metadata(url: str) -> dict:
        return metadata

    async def fake_jwks(url: str) -> KeySet:
        return keyset

    monkeypatch.setattr(oauth_module, "_fetch_metadata", fake_metadata)
    monkeypatch.setattr(oauth_module, "_fetch_jwks", fake_jwks)
    clear_cache()
    yield
    clear_cache()


def _provider() -> OIDCProvider:
    return OIDCProvider(
        name="google",
        discovery_url=GOOGLE_DISCOVERY,
        client_id="client-abc",
        client_secret="secret-xyz",
    )


def _sign_id_token(
    priv: RSAKey,
    *,
    iss: str = MOCK_ISSUER,
    aud: str = "client-abc",
    sub: str = "google-user-123",
    email: str = "user@test.local",
    email_verified: bool = True,
    nonce: str,
    exp_offset: int = 3600,
    extra: dict | None = None,
) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=exp_offset)).timestamp()),
    }
    if extra:
        claims.update(extra)
    return joserfc_jwt.encode(
        {"alg": "RS256", "kid": "provider-1"}, claims, priv
    )


async def test_start_builds_authorize_url_with_pkce(
    jwt_keys: Path, mock_discovery: None
) -> None:
    """GIVEN a provider WHEN start is called THEN URL has client_id + state + code_challenge + nonce."""
    provider = _provider()
    url, state_token, code_verifier = await provider.start(
        redirect_uri="https://app.test/cb", redirect_to="/dashboard"
    )

    assert url.startswith(MOCK_AUTHZ)
    assert "client_id=client-abc" in url
    assert "code_challenge=" in url
    assert "code_challenge_method=S256" in url
    assert f"state={state_token}" in url
    assert "nonce=" in url
    assert len(code_verifier) > 40
    assert state_token  # signed JWT


async def test_complete_happy_path_returns_claims(
    jwt_keys: Path,
    mock_discovery: None,
    provider_keypair: tuple[RSAKey, KeySet],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN matching state + valid id_token WHEN complete is called THEN claims are returned."""
    priv, _ = provider_keypair
    provider = _provider()
    nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/dashboard", nonce=nonce)
    id_token = _sign_id_token(priv, nonce=nonce)

    async def fake_fetch_token(self, *args, **kwargs):
        return {"id_token": id_token, "access_token": "AT"}

    monkeypatch.setattr(AsyncOAuth2Client, "fetch_token", fake_fetch_token)

    result = await provider.complete(
        code="auth-code-from-redirect",
        state_token=state_token,
        code_verifier="verifier-x",
        redirect_uri="https://app.test/cb",
    )

    assert isinstance(result, OAuthIdentityClaims)
    assert result.provider == "google"
    assert result.provider_uid == "google-user-123"
    assert result.email == "user@test.local"
    assert result.email_verified is True
    assert result.redirect_to == "/dashboard"


async def test_complete_rejects_state_for_other_provider(
    jwt_keys: Path, mock_discovery: None
) -> None:
    """GIVEN a state minted for microsoft WHEN completing as google THEN OAuthStateInvalid raises."""
    provider = _provider()  # google
    state_token = mint_state(
        provider="microsoft", redirect_to="/", nonce=generate_nonce()
    )

    with pytest.raises(OAuthStateInvalidError):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


async def test_complete_rejects_id_token_with_wrong_nonce(
    jwt_keys: Path,
    mock_discovery: None,
    provider_keypair: tuple[RSAKey, KeySet],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN id_token with a nonce ≠ state nonce WHEN completing THEN OAuthIdTokenInvalid raises."""
    priv, _ = provider_keypair
    provider = _provider()
    state_nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/", nonce=state_nonce)
    bad_id_token = _sign_id_token(priv, nonce="not-the-real-nonce")

    monkeypatch.setattr(
        AsyncOAuth2Client,
        "fetch_token",
        AsyncMock(return_value={"id_token": bad_id_token}),
    )

    with pytest.raises(OAuthIdTokenInvalidError, match="nonce"):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


async def test_complete_rejects_id_token_with_wrong_aud(
    jwt_keys: Path,
    mock_discovery: None,
    provider_keypair: tuple[RSAKey, KeySet],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN id_token with aud ≠ our client_id WHEN completing THEN OAuthIdTokenInvalid raises."""
    priv, _ = provider_keypair
    provider = _provider()
    nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/", nonce=nonce)
    bad_id_token = _sign_id_token(priv, nonce=nonce, aud="some-other-client")

    monkeypatch.setattr(
        AsyncOAuth2Client,
        "fetch_token",
        AsyncMock(return_value={"id_token": bad_id_token}),
    )

    with pytest.raises(OAuthIdTokenInvalidError, match="aud"):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


async def test_complete_rejects_id_token_with_wrong_iss(
    jwt_keys: Path,
    mock_discovery: None,
    provider_keypair: tuple[RSAKey, KeySet],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN id_token signed with wrong iss WHEN completing THEN OAuthIdTokenInvalid raises."""
    priv, _ = provider_keypair
    provider = _provider()
    nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/", nonce=nonce)
    bad_id_token = _sign_id_token(priv, nonce=nonce, iss="https://evil.test")

    monkeypatch.setattr(
        AsyncOAuth2Client,
        "fetch_token",
        AsyncMock(return_value={"id_token": bad_id_token}),
    )

    with pytest.raises(OAuthIdTokenInvalidError, match="iss"):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


async def test_complete_rejects_expired_id_token(
    jwt_keys: Path,
    mock_discovery: None,
    provider_keypair: tuple[RSAKey, KeySet],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN an expired id_token WHEN completing THEN OAuthIdTokenInvalid raises."""
    priv, _ = provider_keypair
    provider = _provider()
    nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/", nonce=nonce)
    expired = _sign_id_token(priv, nonce=nonce, exp_offset=-60)

    monkeypatch.setattr(
        AsyncOAuth2Client,
        "fetch_token",
        AsyncMock(return_value={"id_token": expired}),
    )

    with pytest.raises(OAuthIdTokenInvalidError, match="expired"):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


async def test_complete_rejects_id_token_signed_by_wrong_key(
    jwt_keys: Path,
    mock_discovery: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIVEN id_token signed by a key not in the provider JWKS WHEN completing THEN reject."""
    rogue = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    rogue_priv = RSAKey.import_key(
        rogue.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
        parameters={"kid": "provider-1"},  # match the cached kid so lookup succeeds…
    )
    provider = _provider()
    nonce = generate_nonce()
    state_token = mint_state(provider="google", redirect_to="/", nonce=nonce)
    forged = _sign_id_token(rogue_priv, nonce=nonce)

    monkeypatch.setattr(
        AsyncOAuth2Client,
        "fetch_token",
        AsyncMock(return_value={"id_token": forged}),
    )

    with pytest.raises(OAuthIdTokenInvalidError, match="signature"):
        await provider.complete(
            code="x",
            state_token=state_token,
            code_verifier="v",
            redirect_uri="https://app.test/cb",
        )


def test_microsoft_provider_uid_combines_tid_and_oid() -> None:
    """GIVEN id_token claims with tid + oid WHEN provider_uid is computed THEN '<tid>:<oid>'."""
    p = microsoft_provider()
    uid = p.provider_uid_fn({"sub": "ignored", "tid": "tenant-1", "oid": "user-9"})
    assert uid == "tenant-1:user-9"


def test_google_provider_uid_uses_sub() -> None:
    """GIVEN Google id_token claims WHEN provider_uid is computed THEN 'sub' is returned."""
    p = google_provider()
    uid = p.provider_uid_fn({"sub": "117392", "email": "..."})
    assert uid == "117392"
