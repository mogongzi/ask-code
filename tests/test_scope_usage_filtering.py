"""
Test scope usage filtering to eliminate false positives.

Verifies that ScopeDefinitionRule correctly:
1. Identifies actual scope calls (.for_custom_domain)
2. Rejects generic ActiveRecord methods (.find_by, .where)
3. Rejects association declarations (has_many)
"""
import pytest
from tools.components.rails_search_rules import ScopeDefinitionRule


class TestScopeUsageFiltering:
    """Test scope usage vs false positive filtering."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ScopeDefinitionRule()

        # Mock SQL analysis
        class MockColumn:
            def __init__(self, name):
                self.name = name
                self.is_foreign_key = False

        class MockCondition:
            def __init__(self, column_name):
                self.column = MockColumn(column_name)

        class MockSQLAnalysis:
            primary_model = "CustomDomainTombstone"
            raw_sql = "SELECT * FROM custom_domain_tombstones WHERE custom_domain = ?"
            has_limit = True
            has_offset = False
            has_order = False

            def __init__(self):
                self.where_conditions = [
                    MockCondition("custom_domain")
                ]

        self.sql_analysis = MockSQLAnalysis()

    def test_actual_scope_call_is_accepted(self):
        """Scope usage should be accepted with high confidence."""
        match = {
            "file": "lib/multi_domain.rb",
            "line": 43,
            "content": "CustomDomainTombstone.for_custom_domain(request_host).take",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        # Should have non-zero confidence (actual scope call)
        assert confidence > 0.0, "Actual scope call should be accepted"

    def test_find_by_is_rejected(self):
        """find_by calls should be rejected (not scope usage)."""
        match = {
            "file": "app/models/company.rb",
            "line": 2435,
            "content": "CustomDomainTombstone.find_by(company_id: self.id_in_public_schema, custom_domain: self.custom_domain)",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        # Should be rejected (generic ActiveRecord method)
        assert confidence == 0.0, "find_by should be rejected as false positive"

    def test_find_or_create_by_is_rejected(self):
        """find_or_create_by calls should be rejected."""
        match = {
            "file": "app/models/concerns/multitenancy/company.rb",
            "line": 64,
            "content": "CustomDomainTombstone.find_or_create_by(company_id: self.id_in_public_schema, custom_domain: self.custom_domain)",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        assert confidence == 0.0, "find_or_create_by should be rejected"

    def test_where_is_rejected(self):
        """where calls should be rejected."""
        match = {
            "file": "app/models/concerns/multitenancy/company.rb",
            "line": 52,
            "content": "CustomDomainTombstone.where(company_id: self.id_in_public_schema)",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        assert confidence == 0.0, "where should be rejected"

    def test_has_many_association_is_rejected(self):
        """has_many declarations should be rejected."""
        match = {
            "file": "app/models/company.rb",
            "line": 254,
            "content": "has_many :custom_subdomain_tombstones, -> { CustomDomainTombstone.subdomain }",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        assert confidence == 0.0, "has_many association should be rejected"

    def test_find_from_param_is_rejected(self):
        """Custom finders like find_from_param should be rejected."""
        match = {
            "file": "app/controllers/custom_domain_tombstones_controller.rb",
            "line": 27,
            "content": "CustomDomainTombstone.find_from_param(params[:id])",
            "pattern_type": "where_scope_usage"
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        assert confidence == 0.0, "find_from_param should be rejected"

    def test_scope_definition_is_accepted(self):
        """Scope definitions should be accepted (not marked as usage)."""
        match = {
            "file": "app/models/custom_domain_tombstone.rb",
            "line": 34,
            "content": "scope(:for_custom_domain, lambda do |custom_domain|",
            "pattern_type": "where_scope"  # Different pattern type
        }

        confidence = self.rule.validate_match(match, self.sql_analysis)

        # Should have non-zero confidence (scope definition)
        assert confidence > 0.0, "Scope definition should be accepted"

    def test_build_patterns_includes_specific_scope_names(self):
        """Search patterns should include specific scope names, not generic calls."""
        patterns = self.rule.build_search_patterns(self.sql_analysis)

        # Extract pattern strings
        pattern_strings = [p.pattern for p in patterns]

        # Should include specific scope name patterns
        assert any("for_custom_domain" in p for p in pattern_strings), \
            "Should search for .for_custom_domain() specifically"

        assert any("by_custom_domain" in p for p in pattern_strings), \
            "Should search for .by_custom_domain() as alternative"

        # Should NOT include overly generic pattern like "CustomDomainTombstone\.\w+"
        # (if it does, it should be low priority)
        generic_patterns = [p for p in patterns if r"\.\w+" in p.pattern and "custom_domain" not in p.pattern]
        assert len(generic_patterns) == 0, \
            "Should not use generic model.method pattern that matches everything"
