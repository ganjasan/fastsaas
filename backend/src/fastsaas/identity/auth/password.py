"""Argon2id password hashing per design.md §D8.

Parameters tuned per OWASP password-storage cheat sheet (memory_cost=64 MiB,
time_cost=3, parallelism=4). Verifies in <500ms on dev hardware.

`validate_password_policy` enforces the v1 minimum-length rule (12 chars) and
is called from the register flow before hashing.
"""

from __future__ import annotations

from passlib.context import CryptContext

MIN_PASSWORD_LENGTH = 12

_PASSWORD_CTX = CryptContext(
    schemes=["argon2"],
    argon2__memory_cost=64 * 1024,
    argon2__time_cost=3,
    argon2__parallelism=4,
)


class PasswordTooShortError(ValueError):
    """Raised when a candidate password is shorter than MIN_PASSWORD_LENGTH."""

    code = "auth.password_too_short"


def validate_password_policy(password: str) -> None:
    """Enforce the v1 password policy. Raises PasswordTooShort on failure."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordTooShortError(
            f"password must be at least {MIN_PASSWORD_LENGTH} characters"
        )


def hash_password(password: str) -> str:
    """Validate and Argon2id-hash a password, returning the encoded hash."""
    validate_password_policy(password)
    return _PASSWORD_CTX.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    """Constant-time-ish verification; returns False on any mismatch or malformed hash."""
    try:
        return _PASSWORD_CTX.verify(password, encoded_hash)
    except (ValueError, TypeError):
        return False
