"""Unit tests for `audit.scrub` — filter validation and helper invariants.

DB-touching scrub behaviour (UPDATE, RLS, meta-row, idempotency, cross-org)
is exercised in `test_audit_scrub_integration.py` against the live ASGI app.
This file pins the static / pure-function contract from the audit-pii-scrub
change.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastsaas.audit.intent import PII_INTENT_KEYS
from fastsaas.audit.scrub import (
    SCRUBBED_FIELDS,
    SCRUBBED_GDPR_LITERAL,
    ScrubFilter,
    ScrubRequest,
)


class TestSentinelAndCoverage:
    def test_sentinel_is_distinct_from_redacted(self) -> None:
        # GIVEN the GDPR sentinel
        # WHEN comparing to the at-write-time `<redacted>` literal
        # THEN they differ — reports must distinguish "always redacted" from
        # "scrubbed post-hoc"
        assert SCRUBBED_GDPR_LITERAL == "<scrubbed:gdpr>"
        assert SCRUBBED_GDPR_LITERAL != "<redacted>"

    def test_scrubbed_fields_match_pii_intent_keys(self) -> None:
        # GIVEN scrub.py and intent.py both publish their key lists
        # WHEN comparing them
        # THEN they are the same tuple — drift between the two would mean a
        # client-controlled key reaches immortal storage without an erasure
        # path. The module-level assert in scrub.py also fails loud at
        # import-time; this test is the explicit contract test.
        assert tuple(SCRUBBED_FIELDS) == PII_INTENT_KEYS


class TestScrubFilterValidation:
    def test_empty_filter_is_detected_by_is_empty(self) -> None:
        # GIVEN a filter with no fields populated
        f = ScrubFilter()
        # WHEN is_empty is checked
        # THEN it returns True (route raises 400 with empty_filter code)
        assert f.is_empty()

    def test_filter_with_one_field_is_not_empty(self) -> None:
        # GIVEN a filter with just `ip`
        f = ScrubFilter(ip="203.0.113.4")
        # WHEN is_empty is checked
        # THEN it returns False — at-least-one-field is satisfied
        assert not f.is_empty()

    def test_unknown_filter_key_rejected_at_parse_time(self) -> None:
        # GIVEN a filter with an unknown key (extra=forbid)
        # WHEN ScrubFilter is constructed via model_validate
        # THEN pydantic raises ValidationError with extra_forbidden — the
        # route translates this to HTTP 400 audit.scrub.unknown_filter_key
        with pytest.raises(ValidationError) as exc_info:
            ScrubFilter.model_validate(
                {"actor_id": "00000000-0000-0000-0000-000000000000", "country": "DE"}
            )
        assert any(
            err["type"] == "extra_forbidden" for err in exc_info.value.errors()
        )

    def test_unknown_top_level_request_key_rejected(self) -> None:
        # GIVEN a ScrubRequest body with a typo at the top level
        # WHEN parsed
        # THEN extra_forbidden is raised — the request body is locked too
        with pytest.raises(ValidationError) as exc_info:
            ScrubRequest.model_validate(
                {"filter": {"ip": "1.2.3.4"}, "dryrun": True}  # missing underscore
            )
        assert any(
            err["type"] == "extra_forbidden" for err in exc_info.value.errors()
        )

    def test_valid_filter_with_iso_datetime_parses(self) -> None:
        # GIVEN a filter with `since` as ISO-8601
        f = ScrubFilter.model_validate(
            {"since": "2026-01-01T00:00:00Z", "until": "2026-12-31T23:59:59Z"}
        )
        # WHEN inspecting the parsed datetimes
        # THEN they are present and naive-vs-aware preserved (parser respects tz)
        assert f.since is not None
        assert f.until is not None
        assert not f.is_empty()

    def test_dry_run_defaults_to_false(self) -> None:
        # GIVEN a request without dry_run set
        r = ScrubRequest.model_validate({"filter": {"ip": "1.2.3.4"}})
        # WHEN inspecting the dry_run flag
        # THEN default is wet (false) — destructive default is OK because
        # the gate is the SCRUB capability, not the flag
        assert r.dry_run is False
