"""
Test for INSERT query search fixes.
"""
import pytest
from tools.semantic_sql_analyzer import SemanticSQLAnalyzer, QueryIntent, create_fingerprint


class TestInsertSearchFixes:
    """Test the fixes for INSERT query search."""

    def setup_method(self):
        """Setup test fixtures."""
        self.analyzer = SemanticSQLAnalyzer()

    def test_insert_query_intent_detection(self):
        """Test that INSERT queries are correctly identified."""
        sql = """
        INSERT INTO `page_views`
        (`member_id`, `company_id`, `action`, `controller`)
        VALUES (123, 456, 'show', 'pages')
        """

        analysis = self.analyzer.analyze(sql)

        assert analysis.intent == QueryIntent.DATA_INSERTION
        assert analysis.primary_table is not None
        assert analysis.primary_table.name == "page_views"
        assert analysis.primary_model == "PageView"

    def test_insert_query_fingerprint(self):
        """Test that INSERT queries generate correct fingerprint."""
        sql = """
        INSERT INTO `page_views`
        (`member_id`, `company_id`, `action`, `controller`)
        VALUES (123, 456, 'show', 'pages')
        """

        analysis = self.analyzer.analyze(sql)
        fingerprint = create_fingerprint(analysis)

        assert fingerprint == "INSERT INTO page_views (...)"
        assert fingerprint != "SELECT * FROM table"  # Old buggy behavior

    def test_insert_rails_patterns_generated(self):
        """Test that INSERT queries generate appropriate Rails patterns."""
        sql = """
        INSERT INTO `page_views`
        (`member_id`, `company_id`, `action`, `controller`)
        VALUES (123, 456, 'show', 'pages')
        """

        analysis = self.analyzer.analyze(sql)

        assert len(analysis.rails_patterns) > 0
        assert any("PageView.create" in pattern for pattern in analysis.rails_patterns)
        assert any("PageView.new" in pattern for pattern in analysis.rails_patterns)

    def test_update_query_fingerprint(self):
        """Test that UPDATE queries also get proper fingerprints."""
        sql = "UPDATE page_views SET view_count = 10 WHERE id = 123"

        analysis = self.analyzer.analyze(sql)
        fingerprint = create_fingerprint(analysis)

        assert analysis.intent == QueryIntent.DATA_UPDATE
        assert fingerprint.startswith("UPDATE page_views SET ...")
        assert "WHERE id" in fingerprint  # SQLGlot may use "eq" or "="

    def test_delete_query_fingerprint(self):
        """Test that DELETE queries get proper fingerprints."""
        sql = "DELETE FROM page_views WHERE id = 123"

        analysis = self.analyzer.analyze(sql)
        fingerprint = create_fingerprint(analysis)

        assert analysis.intent == QueryIntent.DATA_DELETION
        assert fingerprint.startswith("DELETE FROM page_views")
        assert "WHERE id" in fingerprint  # SQLGlot may use "eq" or "="

    def test_data_retrieval_with_limit_fingerprint(self):
        """Test that DATA_RETRIEVAL queries with LIMIT include it in fingerprint."""
        sql = "SELECT `custom_domain_tombstones`.* FROM `custom_domain_tombstones` WHERE `custom_domain_tombstones`.`custom_domain` = ? LIMIT ?"

        analysis = self.analyzer.analyze(sql)
        fingerprint = create_fingerprint(analysis)

        assert analysis.intent == QueryIntent.DATA_RETRIEVAL
        assert "LIMIT ?" in fingerprint, f"Fingerprint should include LIMIT clause, got: {fingerprint}"
        # SQLGlot may normalize operators to "eq", "=", etc.
        assert "SELECT * FROM custom_domain_tombstones WHERE custom_domain" in fingerprint
        assert "LIMIT ?" in fingerprint

    def test_data_retrieval_without_limit_fingerprint(self):
        """Test that DATA_RETRIEVAL queries without LIMIT don't include it in fingerprint."""
        sql = "SELECT `custom_domain_tombstones`.* FROM `custom_domain_tombstones` WHERE `custom_domain_tombstones`.`custom_domain` = ?"

        analysis = self.analyzer.analyze(sql)
        fingerprint = create_fingerprint(analysis)

        assert analysis.intent == QueryIntent.DATA_RETRIEVAL
        assert "LIMIT" not in fingerprint, f"Fingerprint should not include LIMIT clause, got: {fingerprint}"
        # SQLGlot may normalize operators to "eq", "=", etc.
        assert "SELECT * FROM custom_domain_tombstones WHERE custom_domain" in fingerprint

    def test_controller_snake_case_conversion(self):
        """Test controller name conversion fix."""
        from tools.controller_analyzer import ControllerAnalyzer

        analyzer = ControllerAnalyzer(project_root="/tmp", debug=False)

        # Test various controller name conversions
        assert analyzer._to_snake_case("WorkPages") == "work_pages"
        assert analyzer._to_snake_case("Users") == "users"
        assert analyzer._to_snake_case("APIController") == "api_controller"
        assert analyzer._to_snake_case("MyBigController") == "my_big_controller"
        assert analyzer._to_snake_case("HTTPRequest") == "http_request"