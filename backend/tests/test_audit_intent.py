"""Unit tests for `audit.intent.compute_intent_hash`.

Covers the prefix-precedence ladder defined in ADR-010 amendment:
agent: > idem: > sess: > req:. Each branch is exercised independently
so a regression on the precedence order surfaces as a single failing
case rather than a vague "wrong prefix" assertion.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from fastsaas.audit.intent import compute_intent_hash


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    """Build a minimal `Request` with custom headers for the unit under test.

    The `compute_intent_hash` API only reads `request.headers`,
    `request.client`, `request.url.path`, and `request.method` — the
    cheapest way to drive it is the raw ASGI scope without a real
    transport.
    """
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "http",
        "server": ("test", 80),
        "path": "/some/path",
        "query_string": b"",
        "headers": headers or [],
        "client": ("203.0.113.4", 12345),
        "root_path": "",
    }
    return Request(scope)


class TestComputeIntentHashPrefixes:
    def test_x_agent_intent_wins_over_idempotency_key(self) -> None:
        # GIVEN both X-Agent-Intent and Idempotency-Key headers
        request = _request(
            [
                (b"x-agent-intent", b"summarise quarter"),
                (b"idempotency-key", b"unused-here"),
            ]
        )
        # WHEN compute_intent_hash inspects the precedence ladder
        intent_hash, metadata = compute_intent_hash(request)
        # THEN agent: prefix wins and the original prompt is preserved
        assert intent_hash.startswith("agent:")
        assert metadata["original_prompt"] == "summarise quarter"

    def test_idem_prefix_when_only_idempotency_key(self) -> None:
        # GIVEN only Idempotency-Key
        request = _request([(b"idempotency-key", b"req-7")])
        # WHEN compute_intent_hash runs
        intent_hash, _ = compute_intent_hash(request)
        # THEN prefix is idem:
        assert intent_hash.startswith("idem:")

    def test_sess_prefix_when_only_session_intent(self) -> None:
        # GIVEN only X-Session-Intent
        request = _request([(b"x-session-intent", b"wizard-1")])
        # WHEN compute_intent_hash runs
        intent_hash, _ = compute_intent_hash(request)
        # THEN prefix is sess:
        assert intent_hash.startswith("sess:")

    def test_req_prefix_with_x_request_id_when_no_other_headers(self) -> None:
        # GIVEN only an X-Request-ID and no intent headers
        request = _request([(b"x-request-id", b"abc-123")])
        # WHEN compute_intent_hash runs
        intent_hash, metadata = compute_intent_hash(request)
        # THEN prefix is req: and the request_id is the X-Request-ID value
        assert intent_hash == "req:abc-123"
        assert metadata["request_id"] == "abc-123"

    def test_req_prefix_synthesises_request_id_when_no_headers(self) -> None:
        # GIVEN a request with no intent / idempotency / request-id headers
        request = _request()
        # WHEN compute_intent_hash falls back
        intent_hash, metadata = compute_intent_hash(request)
        # THEN intent_hash is req:<32-hex-uuid> and request_id matches
        assert intent_hash.startswith("req:")
        rid = metadata["request_id"]
        assert intent_hash == f"req:{rid}"

    def test_metadata_carries_path_method_and_client_ip(self) -> None:
        # GIVEN a typical request
        request = _request([(b"user-agent", b"pytest/1.0")])
        # WHEN compute_intent_hash runs
        _, metadata = compute_intent_hash(request)
        # THEN path / method / ip / user_agent are recorded
        assert metadata["path"] == "/some/path"
        assert metadata["method"] == "GET"
        assert metadata["ip"] == "203.0.113.4"
        assert metadata["user_agent"] == "pytest/1.0"


@pytest.mark.parametrize(
    ("header_name", "header_value", "expected_prefix"),
    [
        (b"x-agent-intent", b"summarise", "agent:"),
        (b"idempotency-key", b"foo-1", "idem:"),
        (b"x-session-intent", b"flow-x", "sess:"),
    ],
)
def test_each_source_prefix_in_isolation(
    header_name: bytes, header_value: bytes, expected_prefix: str
) -> None:
    # GIVEN exactly one source header at a time
    request = _request([(header_name, header_value)])
    # WHEN compute_intent_hash runs
    intent_hash, _ = compute_intent_hash(request)
    # THEN that source's prefix is selected
    assert intent_hash.startswith(expected_prefix)


class TestUnboundedHeadersAreCapped:
    """Authenticated attackers can stamp arbitrarily large header values;
    `audit_log` is immortal, so bounded storage is the only fix once a
    huge header is accepted by the ASGI server. The cap is enforced in
    `intent.py::_bounded` and runs before headers reach storage."""

    def test_oversize_x_agent_intent_truncated_in_metadata(self) -> None:
        # GIVEN an X-Agent-Intent header far above the cap
        big = b"A" * 10_000
        request = _request([(b"x-agent-intent", big)])
        # WHEN compute_intent_hash runs
        _, metadata = compute_intent_hash(request)
        # THEN original_prompt is truncated to the cap (4096 chars)
        assert len(metadata["original_prompt"]) == 4096

    def test_oversize_x_request_id_truncated_in_metadata(self) -> None:
        # GIVEN an X-Request-ID header far above the cap
        request = _request([(b"x-request-id", b"R" * 10_000)])
        # WHEN compute_intent_hash runs
        intent_hash, metadata = compute_intent_hash(request)
        # THEN both the metadata field and the intent_hash itself are bounded
        assert len(metadata["request_id"]) == 4096
        assert intent_hash == f"req:{metadata['request_id']}"
        assert len(intent_hash) <= 4096 + len("req:")

    def test_oversize_user_agent_truncated_in_metadata(self) -> None:
        # GIVEN an enormous User-Agent header
        request = _request([(b"user-agent", b"U" * 10_000)])
        # WHEN compute_intent_hash runs
        _, metadata = compute_intent_hash(request)
        # THEN it's truncated before it reaches the audit row
        assert len(metadata["user_agent"]) == 4096
