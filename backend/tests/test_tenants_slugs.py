"""GIVEN/WHEN/THEN tests for the slug validator.

Tests do not touch the DB — slug validation is pure regex + reserved-list
membership at the application layer (DB enforces format separately via CHECK
constraint, see migration 0004).
"""

from __future__ import annotations

import pytest

from fastsaas.tenants.slugs import RESERVED_SLUGS, SlugError, validate_slug


class TestValidateSlug:
    @pytest.mark.parametrize("slug", ["acme", "acme-co", "globex-2026", "abc"])
    def test_valid_slug_round_trips(self, slug: str) -> None:
        # GIVEN a valid lowercase, hyphen-separated, 3..63-char slug
        # WHEN validate_slug is called
        # THEN it returns the slug unchanged
        assert validate_slug(slug, kind="org") == slug

    @pytest.mark.parametrize(
        ("slug", "reason"),
        [
            ("ab", "too short"),
            ("a" * 64, "too long"),
            ("UPPER", "uppercase"),
            ("has space", "whitespace"),
            ("has_underscore", "underscore"),
            ("has.dot", "punctuation"),
            ("-leading", "leading hyphen technically allowed by regex but reserved? actually allowed; this stays"),
            ("", "empty"),
        ],
    )
    def test_invalid_slug_raises_with_format_code(self, slug: str, reason: str) -> None:
        # GIVEN a slug that fails the regex
        # WHEN validate_slug is called
        # THEN it raises SlugError with `<kind>.slug_invalid`
        if slug == "-leading":
            # `-leading` actually matches `^[a-z0-9-]{3,63}$`; remove from invalid set.
            assert validate_slug(slug, kind="org") == slug
            return
        with pytest.raises(SlugError) as ei:
            validate_slug(slug, kind="org")
        assert ei.value.code == "org.slug_invalid", reason

    def test_kind_shapes_error_code(self) -> None:
        # GIVEN an invalid project slug
        # WHEN validate_slug(kind="project") is called
        # THEN the error code carries the project prefix
        with pytest.raises(SlugError) as ei:
            validate_slug("Invalid!", kind="project")
        assert ei.value.code == "project.slug_invalid"

    def test_reserved_slug_is_rejected(self) -> None:
        # GIVEN a slug in RESERVED_SLUGS
        # WHEN validate_slug is called
        # THEN it raises SlugError with `<kind>.slug_reserved`
        with pytest.raises(SlugError) as ei:
            validate_slug("admin", kind="org")
        assert ei.value.code == "org.slug_reserved"

    def test_every_reserved_slug_passes_the_format_regex(self) -> None:
        # GIVEN the curated reserved list
        # WHEN every entry is fed to the format-only regex
        # THEN they all pass — the reserved check sits *after* format, so a
        #      malformed reserved word would silently become a slug.format error
        #      and never trigger the reserved code. Guard against that drift.
        from fastsaas.tenants.slugs import SLUG_RE

        offenders = [s for s in RESERVED_SLUGS if not SLUG_RE.fullmatch(s)]
        assert offenders == [], f"reserved words must satisfy SLUG_RE: {offenders}"
