"""
Test partial SQL match detection and completeness scoring.

Tests the fix for the issue where agent claimed "EXACT MATCH" for partial
matches that were missing critical SQL conditions (e.g., custom15, ORDER BY, LIMIT/OFFSET).
"""
import pytest
from tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch
from tools.semantic_sql_analyzer import SemanticSQLAnalyzer


class TestPartialSQLMatchDetection:
    """Test suite for partial SQL match detection."""

    def setup_method(self):
        """Set up test fixtures."""
        self.tool = EnhancedSQLRailsSearch(project_root="/fake/project", debug=False)
        self.analyzer = SemanticSQLAnalyzer()

    def test_completeness_scoring_all_conditions_present(self):
        """Test completeness when all SQL conditions are in the code."""
        # SQL with 3 WHERE conditions
        sql = "SELECT * FROM profiles WHERE company_id = 481 AND status = 'active' AND custom15 = 'Y' ORDER BY company_id LIMIT 1000"
        analysis = self.analyzer.analyze(sql)

        # Rails code with all 3 conditions + ORDER + LIMIT
        snippet = "Profile.where(company_id: 481, status: 'active', custom15: 'Y').order(:company_id).limit(1000)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["matched_conditions"] == 3
        assert result["total_conditions"] == 3
        assert result["has_order"] is True
        assert result["has_limit"] is True
        assert result["completeness_score"] >= 0.9
        assert result["confidence"] == "high"
        assert len(result["missing_clauses"]) == 0

    def test_completeness_scoring_missing_one_condition(self):
        """Test completeness when one WHERE condition is missing."""
        # SQL with 3 WHERE conditions
        sql = "SELECT * FROM profiles WHERE company_id = 481 AND status = 'active' AND custom15 = 'Y'"
        analysis = self.analyzer.analyze(sql)

        # Rails code missing custom15 condition
        snippet = "Profile.where(company_id: 481, status: 'active')"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["matched_conditions"] == 2
        assert result["total_conditions"] == 3
        assert result["completeness_score"] < 0.9  # Not high confidence
        assert result["confidence"] in ["medium", "partial"]
        assert "1 WHERE condition(s)" in result["missing_clauses"]

    def test_completeness_scoring_missing_order_by(self):
        """Test completeness when ORDER BY clause is missing."""
        # SQL with ORDER BY
        sql = "SELECT * FROM profiles WHERE company_id = 481 ORDER BY company_id"
        analysis = self.analyzer.analyze(sql)

        # Rails code without .order()
        snippet = "Profile.where(company_id: 481)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["has_order"] is False
        assert "ORDER BY" in result["missing_clauses"]
        assert result["completeness_score"] < 0.9
        assert result["confidence"] in ["medium", "partial"]

    def test_completeness_scoring_missing_limit_offset(self):
        """Test completeness when LIMIT/OFFSET clauses are missing."""
        # SQL with LIMIT and OFFSET
        sql = "SELECT * FROM profiles WHERE company_id = 481 LIMIT 1000 OFFSET 887000"
        analysis = self.analyzer.analyze(sql)

        # Rails code without .limit() or .offset()
        snippet = "Profile.where(company_id: 481)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["has_limit"] is False
        assert result["has_offset"] is False
        assert "LIMIT" in result["missing_clauses"]
        assert "OFFSET" in result["missing_clauses"]
        assert result["completeness_score"] < 0.8

    def test_completeness_scoring_critical_condition_missing(self):
        """Test the original bug case - missing custom15 + ORDER + LIMIT/OFFSET."""
        # The problematic SQL from the bug report
        sql = """
        SELECT `profiles`.* FROM `profiles`
        WHERE `profiles`.`company_id` = 481
          AND ((custom15 = 'Y') AND status = 'active')
        ORDER BY company_id
        LIMIT 1000 OFFSET 887000
        """
        analysis = self.analyzer.analyze(sql)

        # The partial match that was incorrectly marked as "high confidence"
        snippet = "Profile.where(company_id: company_id, id: pids, status: 'active').to_a"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        # Should detect missing custom15, ORDER BY, LIMIT, OFFSET
        assert result["matched_conditions"] < result["total_conditions"]
        assert result["has_order"] is False
        assert result["has_limit"] is False
        assert result["has_offset"] is False
        assert result["completeness_score"] < 0.6  # Low score
        assert result["confidence"] in ["partial", "low"]
        assert len(result["missing_clauses"]) >= 3  # At least 3 missing

    def test_hash_syntax_column_matching(self):
        """Test that column matching works with hash syntax."""
        sql = "SELECT * FROM profiles WHERE company_id = 481 AND status = 'active'"
        analysis = self.analyzer.analyze(sql)

        # Hash syntax: :column_name =>
        snippet = "Profile.where(:company_id => 481, :status => 'active')"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["matched_conditions"] == 2
        assert result["total_conditions"] == 2

    def test_keyword_syntax_column_matching(self):
        """Test that column matching works with keyword syntax."""
        sql = "SELECT * FROM profiles WHERE company_id = 481 AND status = 'active'"
        analysis = self.analyzer.analyze(sql)

        # Keyword syntax: column_name:
        snippet = "Profile.where(company_id: 481, status: 'active')"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["matched_conditions"] == 2
        assert result["total_conditions"] == 2

    def test_order_detection_with_parentheses(self):
        """Test ORDER BY detection with .order() method."""
        sql = "SELECT * FROM profiles WHERE company_id = 481 ORDER BY created_at"
        analysis = self.analyzer.analyze(sql)

        snippet = "Profile.where(company_id: 481).order(:created_at)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["has_order"] is True
        assert "ORDER BY" not in result["missing_clauses"]

    def test_limit_detection_with_take(self):
        """Test LIMIT detection with .take() method."""
        sql = "SELECT * FROM profiles LIMIT 10"
        analysis = self.analyzer.analyze(sql)

        snippet = "Profile.take(10)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["has_limit"] is True
        assert "LIMIT" not in result["missing_clauses"]

    def test_limit_detection_with_first(self):
        """Test LIMIT detection with .first method."""
        sql = "SELECT * FROM profiles LIMIT 1"
        analysis = self.analyzer.analyze(sql)

        snippet = "Profile.first"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["has_limit"] is True
        assert "LIMIT" not in result["missing_clauses"]

    def test_no_conditions_sql(self):
        """Test completeness for SQL with no WHERE conditions."""
        sql = "SELECT * FROM profiles"
        analysis = self.analyzer.analyze(sql)

        snippet = "Profile.all"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["total_conditions"] == 0
        assert result["completeness_score"] == 1.0  # Full score when no conditions needed
        assert result["confidence"] == "high"

    def test_case_insensitive_column_matching(self):
        """Test that column matching is case-insensitive."""
        sql = "SELECT * FROM profiles WHERE COMPANY_ID = 481"
        analysis = self.analyzer.analyze(sql)

        snippet = "Profile.where(company_id: 481)"

        result = self.tool._calculate_match_completeness(snippet, analysis)

        assert result["matched_conditions"] == 1


class TestResponseAnalyzerPartialMatchDetection:
    """Test response analyzer's detection of incomplete SQL matches."""

    def test_detects_missing_conditions_indicator(self):
        """Test detection of 'missing' keywords in response."""
        from agent.response_analyzer import ResponseAnalyzer
        from agent.state_machine import ReActState, ReActStep, StepType

        analyzer = ResponseAnalyzer()
        state = ReActState()
        state.current_step = 2
        state.steps = [
            ReActStep(step_type=StepType.ACTION, content="", tool_name="enhanced_sql_rails_search")
        ]

        response = """
        Found match in app/models/profile.rb:524
        Code: Profile.where(company_id: company_id, status: 'active')

        Missing: custom15 condition, ORDER BY, LIMIT, OFFSET
        """

        result = analyzer._has_incomplete_sql_match(response, state)
        assert result is True

    def test_detects_partial_confidence_indicator(self):
        """Test detection of 'partial' confidence in tool output."""
        from agent.response_analyzer import ResponseAnalyzer
        from agent.state_machine import ReActState, ReActStep, StepType

        analyzer = ResponseAnalyzer()
        state = ReActState()
        state.current_step = 2
        state.steps = [
            ReActStep(step_type=StepType.ACTION, content="", tool_name="enhanced_sql_rails_search")
        ]

        response = """
        Match found with confidence: partial (score: 0.5)
        Matched 2/3 conditions
        """

        result = analyzer._has_incomplete_sql_match(response, state)
        assert result is True

    def test_detects_exact_match_false_claim(self):
        """Test detection of 'EXACT MATCH' claims with missing indicators."""
        from agent.response_analyzer import ResponseAnalyzer
        from agent.state_machine import ReActState, ReActStep, StepType

        analyzer = ResponseAnalyzer()
        state = ReActState()
        state.current_step = 2
        state.steps = [
            ReActStep(step_type=StepType.ACTION, content="", tool_name="enhanced_sql_rails_search")
        ]

        response = """
        ## EXACT MATCH FOUND

        File: app/models/profile.rb:524
        Code: Profile.where(company_id: company_id, status: 'active')

        Missing: custom15 condition
        """

        result = analyzer._has_incomplete_sql_match(response, state)
        assert result is True  # Should catch the false "EXACT MATCH" claim

    def test_allows_finalization_after_step_6(self):
        """Test that partial match detection stops after step 6."""
        from agent.response_analyzer import ResponseAnalyzer
        from agent.state_machine import ReActState

        analyzer = ResponseAnalyzer()
        state = ReActState()
        state.current_step = 7  # Past threshold
        state.steps = [
            {"tool_name": "enhanced_sql_rails_search", "type": "action"}
        ]

        response = """
        Match found but missing some conditions
        """

        result = analyzer._has_incomplete_sql_match(response, state)
        assert result is False  # Should allow finalization

    def test_ignores_non_sql_searches(self):
        """Test that detection only applies to SQL searches."""
        from agent.response_analyzer import ResponseAnalyzer
        from agent.state_machine import ReActState, ReActStep, StepType

        analyzer = ResponseAnalyzer()
        state = ReActState()
        state.current_step = 2
        state.steps = [
            ReActStep(step_type=StepType.ACTION, content="", tool_name="model_analyzer")  # Not SQL search
        ]

        response = """
        Missing some information
        """

        result = analyzer._has_incomplete_sql_match(response, state)
        assert result is False  # Should ignore non-SQL searches
