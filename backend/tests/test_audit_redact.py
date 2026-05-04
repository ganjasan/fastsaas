"""Unit tests for `audit.redact.redact`.

Anchors the layered-denylist contract from ADR-010 amendment §"Sensitive-
field redaction is layered": global denylist + per-call extension; redacted
keys are replaced with the literal string `"<redacted>"` so presence-of-key
remains observable.
"""

from __future__ import annotations

from fastsaas.audit.redact import GLOBAL_REDACT, REDACTED_LITERAL, redact


class TestGlobalRedaction:
    def test_password_hash_redacted_in_after(self) -> None:
        # GIVEN a diff that contains password_hash on the after side
        diff = {"before": {}, "after": {"email": "x@example.com", "password_hash": "argon2-hash"}}
        # WHEN redact runs
        out = redact(diff)
        # THEN password_hash is replaced and email is preserved
        assert out["after"]["password_hash"] == REDACTED_LITERAL
        assert out["after"]["email"] == "x@example.com"

    def test_token_hash_redacted_in_before_and_after(self) -> None:
        # GIVEN a diff with token_hash on both sides
        diff = {
            "before": {"token_hash": "old-hash"},
            "after": {"token_hash": "new-hash"},
        }
        # WHEN redact runs
        out = redact(diff)
        # THEN both sides have the redacted literal, NOT the hashes
        assert out["before"]["token_hash"] == REDACTED_LITERAL
        assert out["after"]["token_hash"] == REDACTED_LITERAL

    def test_global_denylist_covers_known_secret_columns(self) -> None:
        # GIVEN the global denylist
        # WHEN we enumerate it
        # THEN the v1 secret column names from ADR-010 are present
        for name in ("password_hash", "token_hash", "api_key_hash", "client_secret"):
            assert name in GLOBAL_REDACT


class TestPerCallExtension:
    def test_extra_keys_are_redacted_alongside_global(self) -> None:
        # GIVEN a diff with one global secret and one domain-specific one
        diff = {
            "before": {},
            "after": {
                "password_hash": "p",
                "stripe_customer_id": "cus_123",
                "name": "Acme",
            },
        }
        # WHEN redact runs with stripe_customer_id passed in extra
        out = redact(diff, extra={"stripe_customer_id"})
        # THEN both denied keys are masked, the rest preserved
        assert out["after"]["password_hash"] == REDACTED_LITERAL
        assert out["after"]["stripe_customer_id"] == REDACTED_LITERAL
        assert out["after"]["name"] == "Acme"

    def test_extra_does_not_remove_global_protections(self) -> None:
        # GIVEN extra=set() (no extension)
        diff = {"before": {}, "after": {"password_hash": "p"}}
        # WHEN redact runs with empty extra
        out = redact(diff, extra=set())
        # THEN the global denylist still applies
        assert out["after"]["password_hash"] == REDACTED_LITERAL


class TestShapeInvariants:
    def test_missing_sides_default_to_empty_dict(self) -> None:
        # GIVEN a diff with only `after`
        diff = {"after": {"name": "x"}}
        # WHEN redact runs
        out = redact(diff)
        # THEN `before` is `{}` not `None` — readers always see both sides
        assert out["before"] == {}
        assert out["after"] == {"name": "x"}

    def test_redacted_keys_remain_in_dict(self) -> None:
        # GIVEN a diff with a single secret field
        diff = {"before": {}, "after": {"password_hash": "p"}}
        # WHEN redact runs
        out = redact(diff)
        # THEN the key is preserved (presence-of-key is signal); only the
        # value is masked. Compliance officer can tell that this revision
        # carried a password_hash without learning what it was.
        assert "password_hash" in out["after"]
        assert out["after"]["password_hash"] == REDACTED_LITERAL
