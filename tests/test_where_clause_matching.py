"""
Test WHERE clause matching and unified confidence scoring.

Validates:
- WHERE clause parsing from SQL queries
- WHERE clause parsing from Ruby/Rails code
- Semantic condition matching (operators, values)
- Confidence scoring accuracy
- The specific user-reported bug (missing disabler_id IS NULL)
"""
import pytest
from tools.components.where_clause_matcher import (
    WhereClauseParser,
    WhereClauseMatcher,
    NormalizedCondition,
    Operator,
    MatchResult
)
from tools.components.unified_confidence_scorer import (
    UnifiedConfidenceScorer,
    ClausePresence,
    ScoringWeights
)


class TestWhereClauseParser:
    """Test WHERE clause extraction from SQL and Ruby code."""

    def setup_method(self):
        self.parser = WhereClauseParser()

    def test_parse_sql_is_not_null(self):
        """Test parsing IS NOT NULL from SQL."""
        sql = """
        SELECT * FROM members
        WHERE first_login_at IS NOT NULL
          AND login_handle IS NOT NULL
          AND owner_id IS NULL
        """
        conditions = self.parser.parse_sql(sql)

        assert len(conditions) == 3

        # Check first_login_at IS NOT NULL
        first_login = next((c for c in conditions if c.column == "first_login_at"), None)
        assert first_login is not None
        assert first_login.operator == Operator.IS_NOT_NULL

        # Check login_handle IS NOT NULL
        login_handle = next((c for c in conditions if c.column == "login_handle"), None)
        assert login_handle is not None
        assert login_handle.operator == Operator.IS_NOT_NULL

        # Check owner_id IS NULL
        owner = next((c for c in conditions if c.column == "owner_id"), None)
        assert owner is not None
        assert owner.operator == Operator.IS_NULL

    def test_parse_sql_with_equality(self):
        """Test parsing equality conditions from SQL."""
        sql = "SELECT * FROM members WHERE company_id = 123 AND status != 'archived'"
        conditions = self.parser.parse_sql(sql)

        assert len(conditions) == 2

        company_cond = next((c for c in conditions if c.column == "company_id"), None)
        assert company_cond is not None
        assert company_cond.operator == Operator.EQ
        assert str(company_cond.value) == "123"

        status_cond = next((c for c in conditions if c.column == "status"), None)
        assert status_cond is not None
        assert status_cond.operator == Operator.NEQ

    def test_parse_ruby_where_string(self):
        """Test parsing WHERE from Ruby string syntax."""
        code = """
        @company.members.where("first_login_at IS NOT NULL AND login_handle is NOT NULL AND owner_id IS NULL")
        """
        conditions = self.parser.parse_ruby_code(code)

        # NOTE: Parser correctly detects @company.members association and adds implicit company_id condition
        assert len(conditions) == 4  # 3 from WHERE string + 1 from association (company_id)

        first_login = next((c for c in conditions if c.column == "first_login_at"), None)
        assert first_login is not None
        assert first_login.operator == Operator.IS_NOT_NULL

    def test_parse_ruby_where_hash(self):
        """Test parsing WHERE from Ruby hash syntax."""
        code = "Member.where(company_id: company.id, status: 'active')"
        conditions = self.parser.parse_ruby_code(code)

        assert len(conditions) == 2

        company_cond = next((c for c in conditions if c.column == "company_id"), None)
        assert company_cond is not None
        assert company_cond.operator == Operator.EQ

    def test_parse_ruby_where_nil(self):
        """Test parsing nil values in Ruby."""
        code = "Member.where(disabler_id: nil)"
        conditions = self.parser.parse_ruby_code(code)

        assert len(conditions) == 1
        assert conditions[0].column == "disabler_id"
        assert conditions[0].operator == Operator.IS_NULL


class TestWhereClauseMatcher:
    """Test semantic matching of WHERE clauses."""

    def setup_method(self):
        self.matcher = WhereClauseMatcher()

    def test_perfect_match(self):
        """Test perfect WHERE clause match."""
        sql_conditions = [
            NormalizedCondition("first_login_at", Operator.IS_NOT_NULL),
            NormalizedCondition("owner_id", Operator.IS_NULL),
        ]

        code_conditions = [
            NormalizedCondition("first_login_at", Operator.IS_NOT_NULL),
            NormalizedCondition("owner_id", Operator.IS_NULL),
        ]

        result = self.matcher.match(sql_conditions, code_conditions)

        assert len(result.matched) == 2
        assert len(result.missing) == 0
        assert len(result.extra) == 0
        assert result.match_percentage == 1.0
        assert result.is_perfect_match

    def test_missing_condition(self):
        """Test detection of missing WHERE condition."""
        sql_conditions = [
            NormalizedCondition("first_login_at", Operator.IS_NOT_NULL),
            NormalizedCondition("login_handle", Operator.IS_NOT_NULL),
            NormalizedCondition("owner_id", Operator.IS_NULL),
            NormalizedCondition("disabler_id", Operator.IS_NULL),  # This is missing in code
        ]

        code_conditions = [
            NormalizedCondition("first_login_at", Operator.IS_NOT_NULL),
            NormalizedCondition("login_handle", Operator.IS_NOT_NULL),
            NormalizedCondition("owner_id", Operator.IS_NULL),
            # Missing disabler_id IS NULL
        ]

        result = self.matcher.match(sql_conditions, code_conditions)

        assert len(result.matched) == 3
        assert len(result.missing) == 1
        assert result.missing[0].column == "disabler_id"
        assert result.missing[0].operator == Operator.IS_NULL
        assert result.match_percentage == 0.75  # 3 out of 4
        assert not result.is_complete_match

    def test_operator_mismatch(self):
        """Test that IS NULL vs IS NOT NULL are not matched."""
        sql_conditions = [
            NormalizedCondition("disabler_id", Operator.IS_NULL),
        ]

        code_conditions = [
            NormalizedCondition("disabler_id", Operator.IS_NOT_NULL),  # Wrong operator!
        ]

        result = self.matcher.match(sql_conditions, code_conditions)

        assert len(result.matched) == 0
        assert len(result.missing) == 1
        assert result.match_percentage == 0.0

    def test_extra_conditions_allowed(self):
        """Test that extra conditions in code don't break match."""
        sql_conditions = [
            NormalizedCondition("company_id", Operator.EQ, value="123"),
        ]

        code_conditions = [
            NormalizedCondition("company_id", Operator.EQ, value="123"),
            NormalizedCondition("status", Operator.EQ, value="active"),  # Extra
        ]

        result = self.matcher.match(sql_conditions, code_conditions)

        assert len(result.matched) == 1
        assert len(result.extra) == 1
        assert result.match_percentage == 1.0
        assert result.is_complete_match  # All SQL conditions matched


class TestUserReportedBug:
    """Test the specific bug reported by the user."""

    def setup_method(self):
        self.matcher = WhereClauseMatcher()
        self.scorer = UnifiedConfidenceScorer()

    def test_user_contribution_false_positive(self):
        """
        Test the actual bug: user_contribution.rb was scored 94% confidence
        despite missing disabler_id IS NULL condition.

        Expected: Should be max 40% confidence (missing WHERE condition).
        """
        # SQL query (what the user searched for)
        sql = """
        SELECT * FROM members
        WHERE first_login_at IS NOT NULL
          AND login_handle IS NOT NULL
          AND owner_id IS NULL
          AND disabler_id IS NULL
        ORDER BY id ASC
        LIMIT 1000
        OFFSET 0
        """

        # Code from user_contribution.rb (actual code found)
        code = """
        @company.members.where("first_login_at IS NOT NULL AND login_handle is NOT NULL AND owner_id IS NULL")
            .offset((page-1)*page_size).limit(page_size).order(id: :asc)
        """

        # Parse conditions
        sql_conditions = self.matcher.parser.parse_sql(sql)
        code_conditions = self.matcher.parser.parse_ruby_code(code)

        # Match
        match_result = self.matcher.match(sql_conditions, code_conditions)

        # Verify match result
        assert len(match_result.matched) == 3, "Should match 3 conditions"
        assert len(match_result.missing) == 1, "Should have 1 missing condition"
        assert match_result.missing[0].column == "disabler_id", "Should identify missing disabler_id"
        assert match_result.match_percentage == 0.75, "Should be 75% match (3/4)"

        # Score the match
        clause_presence = ClausePresence(
            sql_has_where=True,
            sql_has_order=True,
            sql_has_limit=True,
            sql_has_offset=True,
            code_has_where=True,
            code_has_order=True,
            code_has_limit=True,
            code_has_offset=True
        )

        scoring_result = self.scorer.score_match(
            match_result,
            clause_presence,
            pattern_distinctiveness=0.5
        )

        confidence = scoring_result["confidence"]

        # CRITICAL ASSERTION: Confidence should be capped at 40% due to missing WHERE condition
        assert confidence <= 0.40, f"Confidence should be max 40% with missing WHERE condition, got {confidence:.2%}"
        assert "Missing" in " ".join(scoring_result["why"]), "Should explain missing conditions"

    def test_update_company_eula_perfect_match(self):
        """
        Test that update_company_eula_version.rb with perfect match gets high confidence.
        """
        # SQL query
        sql = """
        SELECT * FROM members
        WHERE company_id = 123
        ORDER BY id ASC
        LIMIT 1000
        OFFSET 0
        """

        # Code with perfect match
        code = """
        Member.where(company_id: eula.company_id)
            .order(id: :asc)
            .offset((page-1) * VC_PAGE_SIZE)
            .limit(VC_PAGE_SIZE)
        """

        # Parse and match
        sql_conditions = self.matcher.parser.parse_sql(sql)
        code_conditions = self.matcher.parser.parse_ruby_code(code)
        match_result = self.matcher.match(sql_conditions, code_conditions)

        # Verify perfect match
        assert len(match_result.matched) == 1
        assert len(match_result.missing) == 0
        assert match_result.is_complete_match

        # Score
        clause_presence = ClausePresence(
            sql_has_where=True,
            sql_has_order=True,
            sql_has_limit=True,
            sql_has_offset=True,
            code_has_where=True,
            code_has_order=True,
            code_has_limit=True,
            code_has_offset=True
        )

        scoring_result = self.scorer.score_match(
            match_result,
            clause_presence,
            pattern_distinctiveness=0.8
        )

        confidence = scoring_result["confidence"]

        # Perfect match should have high confidence
        assert confidence >= 0.80, f"Perfect match should have >=80% confidence, got {confidence:.2%}"


class TestUnifiedConfidenceScorer:
    """Test confidence scoring with various scenarios."""

    def setup_method(self):
        self.scorer = UnifiedConfidenceScorer()

    def test_strict_penalty_for_missing_where(self):
        """Test that missing WHERE conditions heavily penalize confidence."""
        # 3 out of 4 WHERE conditions matched
        match_result = MatchResult(
            matched=[
                NormalizedCondition("col1", Operator.IS_NOT_NULL),
                NormalizedCondition("col2", Operator.IS_NOT_NULL),
                NormalizedCondition("col3", Operator.IS_NULL),
            ],
            missing=[
                NormalizedCondition("col4", Operator.IS_NULL),
            ],
            extra=[],
            match_percentage=0.75
        )

        clause_presence = ClausePresence(
            sql_has_where=True,
            code_has_where=True,
            sql_has_order=False,
            code_has_order=False,
            sql_has_limit=False,
            code_has_limit=False,
            sql_has_offset=False,
            code_has_offset=False
        )

        result = self.scorer.score_match(match_result, clause_presence)

        # With missing WHERE condition, confidence should be capped at 40%
        assert result["confidence"] <= 0.40

    def test_perfect_score_all_match(self):
        """Test that perfect match gets high confidence."""
        match_result = MatchResult(
            matched=[
                NormalizedCondition("col1", Operator.IS_NOT_NULL),
                NormalizedCondition("col2", Operator.EQ, value="123"),
            ],
            missing=[],
            extra=[],
            match_percentage=1.0
        )

        clause_presence = ClausePresence(
            sql_has_where=True,
            code_has_where=True,
            sql_has_order=True,
            code_has_order=True,
            sql_has_limit=True,
            code_has_limit=True,
            sql_has_offset=False,
            code_has_offset=False
        )

        result = self.scorer.score_match(match_result, clause_presence, pattern_distinctiveness=0.8)

        # Perfect match should score very high
        assert result["confidence"] >= 0.85

    def test_missing_order_by_with_pagination(self):
        """Test penalty for missing ORDER BY when pagination present."""
        match_result = MatchResult(
            matched=[NormalizedCondition("col1", Operator.EQ, value="123")],
            missing=[],
            extra=[],
            match_percentage=1.0
        )

        clause_presence = ClausePresence(
            sql_has_where=True,
            code_has_where=True,
            sql_has_order=True,  # SQL has ORDER BY
            code_has_order=False,  # Code missing ORDER BY
            sql_has_limit=True,  # Pagination present
            code_has_limit=True,
            sql_has_offset=False,
            code_has_offset=False
        )

        result = self.scorer.score_match(match_result, clause_presence)

        # Should be penalized for missing ORDER BY with pagination
        assert result["confidence"] <= 0.60
        assert any("ORDER BY" in str(why) for why in result["why"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
