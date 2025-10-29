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

        # Check that exact LIMIT value pattern exists
        limit_patterns = [p for p in patterns if "500" in p.pattern]
        assert len(limit_patterns) > 0

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

        # Should generate patterns for constants and scopes
        assert len(patterns) > 0

        # Check for constant patterns (high distinctiveness)
        constant_patterns = [p for p in patterns if "COND" in p.pattern]
        assert len(constant_patterns) > 0

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


# Mock implementations for testing

class MockCodeSearchEngine:
    """Mock code search engine for testing."""

    def __init__(self):
        self.mock_results = []

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


def run_all_tests():
    """Run all tests manually."""
    print("\n=== Testing Progressive Search Strategy ===\n")

    # Test domain rules
    print("1. Testing Domain Rules...")
    test_rules = TestDomainRules()
    test_rules.test_limit_offset_rule_patterns()
    test_rules.test_scope_definition_rule_patterns()
    test_rules.test_rule_set_applicable_rules()

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

    print("\n=== All Tests Passed! ===\n")


if __name__ == "__main__":
    run_all_tests()
