"""Argon2id hashing and policy enforcement."""

from __future__ import annotations

import pytest

from fastsaas.identity.auth.password import (
    MIN_PASSWORD_LENGTH,
    PasswordTooShortError,
    hash_password,
    validate_password_policy,
    verify_password,
)


def test_hash_then_verify_roundtrip() -> None:
    """GIVEN a strong password WHEN hashed and verified THEN verification succeeds."""
    encoded = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", encoded) is True


def test_verify_rejects_wrong_password() -> None:
    """GIVEN a stored hash WHEN verifying a different password THEN it returns False."""
    encoded = hash_password("correct horse battery staple")
    assert verify_password("incorrect horse battery staple", encoded) is False


def test_verify_handles_malformed_hash() -> None:
    """GIVEN garbage where a hash should be WHEN verifying THEN it returns False without raising."""
    assert verify_password("anything", "not-a-real-hash") is False


def test_short_password_rejected_at_policy() -> None:
    """GIVEN an under-length password WHEN policy is checked THEN PasswordTooShortError raises."""
    short = "a" * (MIN_PASSWORD_LENGTH - 1)
    with pytest.raises(PasswordTooShortError) as exc:
        validate_password_policy(short)
    assert exc.value.code == "auth.password_too_short"


def test_short_password_rejected_at_hash() -> None:
    """GIVEN an under-length password WHEN hashing THEN PasswordTooShortError raises before any work."""
    with pytest.raises(PasswordTooShortError):
        hash_password("a" * (MIN_PASSWORD_LENGTH - 1))


def test_minimum_length_password_accepted() -> None:
    """GIVEN a password at the threshold WHEN hashed THEN it succeeds."""
    encoded = hash_password("a" * MIN_PASSWORD_LENGTH)
    assert verify_password("a" * MIN_PASSWORD_LENGTH, encoded) is True


def test_argon2_hash_format() -> None:
    """GIVEN a hashed password WHEN inspecting the encoded form THEN it carries the argon2id marker."""
    encoded = hash_password("correct horse battery staple")
    assert encoded.startswith("$argon2id$")
