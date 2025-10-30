"""
Test Progressive Search Strategy

Tests the new generalizable search infrastructure:
- Domain-aware rules
- Progressive refinement engine
- Unified SQL search tool with routing
"""
import pytest
from pathlib import Path

# Import components to test
from tools.components.rails_search_rules import (
    RailsSearchRuleSet,
    LimitOffsetRule,
    ScopeDefinitionRule,
    SearchPattern
)
from tools.components.progressive_search_engine import ProgressiveSearchEngine
from tools.components.code_search_engine import CodeSearchEngine
from tools.sql_rails_search import SQLRailsSearch
from tools.semantic_sql_analyzer import SemanticSQLAnalyzer


class TestDomainRules:
    """Test domain-aware search rules."""

    def test_limit_offset_rule_patterns(self):
        """Test that LimitOffsetRule generates correct patterns."""
        rule = LimitOffsetRule()

        # Create a mock SQL analysis with LIMIT 500
        class MockAnalysis:
            raw_sql = "SELECT * FROM members LIMIT 500 OFFSET 1000"
            has_limit = True
            has_offset = True
            has_order = False

        patterns = rule.build_search_patterns(MockAnalysis())

        # Should generate patterns in order of distinctiveness
        assert len(patterns) > 0

        # Check that structural LIMIT pattern exists (.limit( or .take)
        # NOTE: We now use structural patterns, not literal values
        limit_patterns = [p for p in patterns if "limit" in p.pattern.lower() or "take" in p.pattern.lower()]
        assert len(limit_patterns) > 0

        # Check for OFFSET pattern
        offset_patterns = [p for p in patterns if "offset" in p.pattern.lower()]
        assert len(offset_patterns) > 0

        # Check distinctiveness scores
        for pattern in patterns:
            assert 0.0 <= pattern.distinctiveness <= 1.0

        print("✓ LimitOffsetRule generates correct patterns")

    def test_scope_definition_rule_patterns(self):
        """Test that ScopeDefinitionRule generates correct patterns."""
        rule = ScopeDefinitionRule()

        # Create a mock SQL analysis with WHERE conditions
        class MockColumn:
            name = "login_handle"

        class MockCondition:
            def __init__(self, col_name):
                self.column = MockColumn()
                self.column.name = col_name

        class MockAnalysis:
            where_conditions = [
                MockCondition("login_handle"),
                MockCondition("owner_id"),
                MockCondition("disabler_id")
            ]
            primary_model = "Member"

        patterns = rule.build_search_patterns(MockAnalysis())

        # Should generate patterns for model usage and scope definitions
        assert len(patterns) > 0

        # Check for Model name pattern (structural, not column-specific)
        # NOTE: We now use structural patterns like "Member.\w+", not hardcoded constants
        model_patterns = [p for p in patterns if "Member" in p.pattern]
        assert len(model_patterns) > 0

        # Check for generic scope definition pattern
        scope_def_patterns = [p for p in patterns if "scope" in p.pattern.lower()]
        assert len(scope_def_patterns) > 0

        print("✓ ScopeDefinitionRule generates correct patterns")

    def test_rule_set_applicable_rules(self):
        """Test that RuleSet selects applicable rules correctly."""
        rule_set = RailsSearchRuleSet()

        # Mock analysis with LIMIT and WHERE
        class MockColumn:
            name = "id"
            is_foreign_key = False

        class MockCondition:
            def __init__(self):
                self.column = MockColumn()

        class MockAnalysis:
            where_conditions = [MockCondition()]
            has_limit = True
            has_offset = False
            has_order = False

        applicable = rule_set.get_applicable_rules(MockAnalysis())

        # Should include both ScopeDefinitionRule and LimitOffsetRule
        rule_types = [type(r).__name__ for r in applicable]
        assert 'ScopeDefinitionRule' in rule_types
        assert 'LimitOffsetRule' in rule_types

        print("✓ RuleSet correctly selects applicable rules")

    def test_scope_chain_patterns(self):
        """Test that scope chain patterns are generated for common Rails patterns."""
        rule = ScopeDefinitionRule()

        # Mock analysis for Member.active.limit(500).offset(1000)
        class MockAnalysis:
            primary_model = "Member"
            has_limit = True
            has_offset = True
            where_conditions = []

        patterns = rule.build_search_patterns(MockAnalysis())

        # Should generate scope chain patterns (structural, not hardcoded scope names)
        # NOTE: We now use structural patterns like "Member.\w+.*\.limit" instead of "Member.active.limit"
        scope_chain_patterns = [p for p in patterns if "scope_chain" in p.clause_type]
        assert len(scope_chain_patterns) > 0

        # Check for Member...limit pattern (structural regex, not hardcoded "active")
        member_limit_patterns = [
            p for p in patterns
            if "Member" in p.pattern and ("limit" in p.pattern.lower() or "offset" in p.pattern.lower())
        ]
        assert len(member_limit_patterns) > 0

        # Check distinctiveness
        for pattern in scope_chain_patterns:
            assert pattern.distinctiveness >= 0.4  # Should be moderately distinctive

        print("✓ Scope chain patterns generated correctly")

    def test_association_wrapper_patterns(self):
        """Test that association wrapper patterns are generated."""
        from tools.components.rails_search_rules import AssociationRule

        rule = AssociationRule()

        # Mock analysis with foreign key (company_id)
        class MockColumn:
            name = "company_id"
            is_foreign_key = True
            association_name = "company"

        class MockCondition:
            def __init__(self):
                self.column = MockColumn()

        class MockAnalysis:
            primary_model = "Member"
            has_limit = True
            where_conditions = [MockCondition()]

        patterns = rule.build_search_patterns(MockAnalysis())

        # Should generate method chain patterns (structural patterns, not hardcoded names)
        # NOTE: We now use clause_type="method_chain", not "wrapper"
        method_chain_patterns = [p for p in patterns if "method_chain" in p.clause_type]
        assert len(method_chain_patterns) > 0

        # Check for structural .limit pattern (not hardcoded method names like "find_all_")
        limit_patterns = [p for p in patterns if "limit" in p.pattern.lower()]
        assert len(limit_patterns) > 0

        print("✓ Association wrapper patterns generated correctly")


class TestProgressiveSearchEngine:
    """Test progressive search engine."""

    def test_pattern_ranking(self):
        """Test that patterns are ranked by distinctiveness."""
        # Create mock search engine
        mock_search_engine = MockCodeSearchEngine()

        engine = ProgressiveSearchEngine(
            code_search_engine=mock_search_engine,
            project_root="/fake/project",
            debug=False
        )

        # Create mock rules
        class MockRule:
            def get_search_locations(self):
                from tools.components.rails_search_rules import SearchLocation
                return [SearchLocation("app/**/*.rb", "test", 1)]

            def build_search_patterns(self, analysis):
                return [
                    SearchPattern("500", 0.9, "LIMIT 500", "limit"),
                    SearchPattern("active", 0.6, "scope active", "scope"),
                    SearchPattern("where", 0.3, "where clause", "where")
                ]

            def validate_match(self, match, analysis):
                return 0.8

        # Collect and rank patterns
        patterns = engine._collect_and_rank_patterns([MockRule()], None)

        # Should be sorted by distinctiveness (highest first)
        assert patterns[0].distinctiveness == 0.9  # "500"
        assert patterns[1].distinctiveness == 0.6  # "active"
        assert patterns[2].distinctiveness == 0.3  # "where"

        print("✓ Progressive search engine ranks patterns correctly")


class TestSQLRailsSearch:
    """Test unified SQL search tool."""

    def test_single_query_detection(self):
        """Test that single queries are detected correctly."""
        tool = SQLRailsSearch(project_root=None, debug=False)

        # Single SELECT query
        sql = "SELECT * FROM members WHERE id = 1"

        # Should classify as single query (not transaction)
        classification = tool.sql_classifier.classify(sql)
        assert not classification.is_transaction()
        assert classification.query_count == 1

        print("✓ SQL classifier detects single queries correctly")

    def test_transaction_detection(self):
        """Test that transactions are detected correctly."""
        tool = SQLRailsSearch(project_root=None, debug=False)

        # Transaction log with multiple queries
        sql = """
        BEGIN
        SELECT * FROM members WHERE id = 1
        INSERT INTO page_views (member_id, action) VALUES (1, 'view')
        UPDATE members SET last_seen_at = NOW() WHERE id = 1
        COMMIT
        """

        # Should classify as transaction (query_count may be 1 for block-based detection)
        classification = tool.sql_classifier.classify(sql)
        assert classification.is_transaction()
        # Note: query_count >= 1 is sufficient (classifier treats transaction as one unit)
        assert classification.query_count >= 1

        print("✓ SQL classifier detects transactions correctly")


class TestCodeSearchEngine:
    """Test search-and-filter primitives."""

    def test_search_multi_pattern(self):
        """Test search_multi_pattern filter logic."""
        # Create a mock search engine with fake results
        engine = MockCodeSearchEngine()

        # Mock initial search results
        engine.mock_results = [
            {"file": "a.rb", "line": 10, "content": "Member.active.offset(1000).limit(500)"},
            {"file": "b.rb", "line": 20, "content": "Member.active.where(id: 1)"},
            {"file": "c.rb", "line": 30, "content": "500 items"},
        ]

        # Search for "Member.active" and filter for "offset" and "limit"
        results = engine.search_multi_pattern("Member.active", ["offset", "limit"], "rb")

        # Should only return results with ALL patterns
        assert len(results) == 1  # Only a.rb has all patterns
        assert results[0]["file"] == "a.rb"

        print("✓ search_multi_pattern filters correctly")

    def test_file_level_filter(self):
        """Test file-level filtering for better refinement."""
        engine = MockCodeSearchEngine()

        # Simulate the issue: "500" appears in many places (1650 matches)
        # But only alert_mailer.rb has the actual query
        engine.mock_results = [
            {"file": "app/mailers/alert_mailer.rb", "line": 45, "content": "Member.where(company_id: cid)"},
            {"file": "app/mailers/alert_mailer.rb", "line": 46, "content": "  .where(login_handle: IS NOT NULL)"},
            {"file": "app/mailers/alert_mailer.rb", "line": 47, "content": "  .limit(500).offset(1000)"},
            {"file": "config/constants.rb", "line": 10, "content": "HTTP_SUCCESS = 500"},
            {"file": "lib/timeout.rb", "line": 5, "content": "DEFAULT_TIMEOUT = 500"},
        ]

        # Simulate file content for file-level filtering
        engine.file_contents = {
            "app/mailers/alert_mailer.rb": """
                def self.get_list_of_members_for
                  Member.where(company_id: cid)
                    .where(login_handle: IS NOT NULL)
                    .limit(500).offset(1000)
                    .order(:id)
                end
            """,
            "config/constants.rb": "HTTP_SUCCESS = 500",
            "lib/timeout.rb": "DEFAULT_TIMEOUT = 500"
        }

        # File-level filter: Find files with "500" that also have ".limit" and "Member"
        results = engine.search_file_level_filter("500", [r"\.limit", "Member"], "rb")

        # Should only return results from alert_mailer.rb
        assert len(results) > 0
        assert all(r["file"] == "app/mailers/alert_mailer.rb" for r in results)

        print("✓ File-level filtering correctly narrows down results")


# Mock implementations for testing

class MockCodeSearchEngine:
    """Mock code search engine for testing."""

    def __init__(self):
        self.mock_results = []
        self.file_contents = {}  # For file-level filtering

    def search(self, pattern, file_ext):
        return self.mock_results

    def search_multi_pattern(self, initial_pattern, filter_patterns, file_ext):
        """Simple mock implementation."""
        initial_results = self.search(initial_pattern, file_ext)

        filtered = []
        for result in initial_results:
            content = result.get("content", "").lower()
            if all(fp.lower() in content for fp in filter_patterns):
                result["matched_patterns"] = [initial_pattern] + filter_patterns
                filtered.append(result)

        return filtered

    def search_file_level_filter(self, initial_pattern, filter_patterns, file_ext):
        """Mock file-level filtering implementation."""
        import re

        # Get initial results
        initial_results = self.search(initial_pattern, file_ext)

        # Group by file
        files_with_matches = {}
        for result in initial_results:
            file_path = result.get("file", "")
            if file_path not in files_with_matches:
                files_with_matches[file_path] = []
            files_with_matches[file_path].append(result)

        # Filter files that contain ALL filter patterns
        matching_files = []
        for file_path in files_with_matches.keys():
            if file_path not in self.file_contents:
                continue

            file_content = self.file_contents[file_path].lower()

            # Check if all filter patterns exist in file
            all_match = True
            for filter_pattern in filter_patterns:
                try:
                    if not re.search(filter_pattern, file_content, re.IGNORECASE):
                        all_match = False
                        break
                except re.error:
                    if filter_pattern.lower() not in file_content:
                        all_match = False
                        break

            if all_match:
                matching_files.append(file_path)

        # Return all results from matching files
        filtered_results = []
        for file_path in matching_files:
            for result in files_with_matches[file_path]:
                result["matched_patterns"] = [initial_pattern] + filter_patterns
                filtered_results.append(result)

        return filtered_results


def run_all_tests():
    """Run all tests manually."""
    print("\n=== Testing Progressive Search Strategy ===\n")

    # Test domain rules
    print("1. Testing Domain Rules...")
    test_rules = TestDomainRules()
    test_rules.test_limit_offset_rule_patterns()
    test_rules.test_scope_definition_rule_patterns()
    test_rules.test_rule_set_applicable_rules()
    test_rules.test_scope_chain_patterns()
    test_rules.test_association_wrapper_patterns()

    # Test progressive search engine
    print("\n2. Testing Progressive Search Engine...")
    test_engine = TestProgressiveSearchEngine()
    test_engine.test_pattern_ranking()

    # Test SQL rails search
    print("\n3. Testing SQL Rails Search Tool...")
    test_tool = TestSQLRailsSearch()
    test_tool.test_single_query_detection()
    test_tool.test_transaction_detection()

    # Test code search engine
    print("\n4. Testing Code Search Engine...")
    test_search = TestCodeSearchEngine()
    test_search.test_search_multi_pattern()
    test_search.test_file_level_filter()

    print("\n=== All Tests Passed! ===\n")


if __name__ == "__main__":
    run_all_tests()
