"""GIVEN/WHEN/THEN tests for the bundle catalogue itself.

These are static-shape tests: they verify the BUNDLES dict is internally
consistent so a typo in `bundles.py` cannot reach `mint_bundle`. DB-touching
behaviour (mint/revoke + RLS) is exercised in `test_authz_service.py` once
that test gets its DB-backed counterpart.
"""

from __future__ import annotations

import pytest

from fastsaas.authz.bundles import (
    BUNDLES,
    PRIMARY_BUNDLES,
    CapabilityTemplate,
    Operation,
    ResourceType,
    Scope,
)


class TestBundleCatalogue:
    def test_every_bundle_has_at_least_one_template(self) -> None:
        # GIVEN every named bundle
        # WHEN inspecting its template list
        # THEN it has at least one CapabilityTemplate (a bundle that mints
        #      nothing would silently fail to grant access)
        empty = [name for name, tmpl in BUNDLES.items() if not tmpl]
        assert empty == [], f"empty bundles: {empty}"

    def test_every_template_is_well_typed(self) -> None:
        # GIVEN every (bundle, template) pair
        # WHEN inspecting types
        # THEN operation, resource_type, and scope are concrete enum values
        for name, templates in BUNDLES.items():
            for t in templates:
                assert isinstance(t, CapabilityTemplate), name
                assert isinstance(t.operation, Operation), (name, t)
                assert isinstance(t.resource_type, ResourceType), (name, t)
                assert isinstance(t.scope, Scope), (name, t)

    @pytest.mark.parametrize("primary", sorted(PRIMARY_BUNDLES))
    def test_primary_bundle_is_present_in_bundles(self, primary: str) -> None:
        # GIVEN the PRIMARY_BUNDLES allowlist
        # WHEN looked up in BUNDLES
        # THEN every entry exists (drift would silently break role display)
        assert primary in BUNDLES

    def test_guest_viewer_uses_resource_scope(self) -> None:
        # GIVEN role:guest_viewer
        # WHEN inspecting template scopes
        # THEN every template uses Scope.RESOURCE so mint_bundle requires a
        #      resource_id — the guest cannot accidentally land on type-wide
        #      grants if a future edit drops the scope keyword
        scopes = {t.scope for t in BUNDLES["role:guest_viewer"]}
        assert scopes == {Scope.RESOURCE}, scopes

    def test_owner_supersedes_admin_capabilities(self) -> None:
        # GIVEN role:owner and role:admin
        # WHEN comparing (operation, resource_type) pairs
        # THEN every pair admin holds is also held by owner. Drift here would
        #      make demotion from owner → admin grant new abilities.
        owner_pairs = {(t.operation, t.resource_type) for t in BUNDLES["role:owner"]}
        admin_pairs = {(t.operation, t.resource_type) for t in BUNDLES["role:admin"]}
        missing = admin_pairs - owner_pairs
        assert not missing, f"admin holds capabilities owner does not: {missing}"

    def test_member_lacks_admin_share_grant(self) -> None:
        # GIVEN role:member
        # WHEN inspecting its operations
        # THEN it never carries admin/share/grant — if it ever did, the UI
        #      "promote to admin" flow would be a no-op
        ops = {t.operation for t in BUNDLES["role:member"]}
        assert Operation.ADMIN not in ops
        assert Operation.SHARE not in ops
        assert Operation.GRANT not in ops

    def test_compliance_officer_only_reads_audit_log(self) -> None:
        # GIVEN role:compliance_officer
        # WHEN inspecting its templates
        # THEN the only operation is read on audit_log — compliance must not
        #      drift into operational data even on a casual edit
        templates = BUNDLES["role:compliance_officer"]
        assert len(templates) == 1
        only = templates[0]
        assert only.operation is Operation.READ
        assert only.resource_type is ResourceType.AUDIT_LOG

    def test_dpo_carries_read_and_scrub_on_audit_log_only(self) -> None:
        # GIVEN role:dpo (Data Protection Officer)
        # WHEN inspecting its templates
        # THEN it has exactly two templates — read + scrub on audit_log,
        #      both self-scoped. Drift here would either leak scrub into
        #      another bundle (compliance officer would gain erase rights)
        #      or grant the DPO operational mutation rights they should
        #      not have under GDPR Art.38(3).
        templates = BUNDLES["role:dpo"]
        assert len(templates) == 2
        ops_resources = {(t.operation, t.resource_type) for t in templates}
        assert ops_resources == {
            (Operation.READ, ResourceType.AUDIT_LOG),
            (Operation.SCRUB, ResourceType.AUDIT_LOG),
        }

    def test_compliance_officer_does_not_carry_scrub(self) -> None:
        # GIVEN role:compliance_officer
        # WHEN scanning its operations
        # THEN scrub is never granted — the read-vs-erase split is the
        #      core GDPR control separation. A regression here would
        #      collapse the two roles silently.
        ops = {t.operation for t in BUNDLES["role:compliance_officer"]}
        assert Operation.SCRUB not in ops

    def test_only_dpo_bundle_carries_scrub(self) -> None:
        # GIVEN every bundle
        # WHEN scanning for templates with Operation.SCRUB
        # THEN exactly one bundle (role:dpo) declares it — scrub is a
        #      narrow capability and should not creep into ops/admin/etc.
        bundles_with_scrub = {
            name
            for name, templates in BUNDLES.items()
            if any(t.operation is Operation.SCRUB for t in templates)
        }
        assert bundles_with_scrub == {"role:dpo"}
