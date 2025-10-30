"""
Test pagination value matching (LIMIT/OFFSET validation).

Validates:
- LIMIT/OFFSET extraction from SQL
- LIMIT/OFFSET extraction from Ruby code
- Constant resolution (VC_PAGE_SIZE = 1000)
- Semantic compatibility checking
- The specific user-reported issue (OFFSET 500 vs page_size 1000)
"""
import pytest
from tools.components.pagination_matcher import (
    PaginationExtractor,
    PaginationMatcher,
    PaginationParams,
    CompatibilityLevel
)
from tools.components.unified_confidence_scorer import (
    UnifiedConfidenceScorer,
    ClausePresence
)
from tools.components.where_clause_matcher import (
    WhereClauseMatcher,
    MatchResult,
    NormalizedCondition,
    Operator
)


class TestPaginationExtractor:
    """Test extraction of LIMIT/OFFSET from SQL and Ruby."""

    def setup_method(self):
        self.extractor = PaginationExtractor()

    def test_extract_limit_from_sql(self):
        """Test extracting LIMIT from SQL."""
        sql = "SELECT * FROM members LIMIT 1000"
        params = self.extractor.extract_from_sql(sql)

        assert params.has_limit
        assert params.limit == 1000
        assert not params.has_offset

    def test_extract_limit_and_offset_from_sql(self):
        """Test extracting both LIMIT and OFFSET."""
        sql = "SELECT * FROM members LIMIT 1000 OFFSET 500"
        params = self.extractor.extract_from_sql(sql)

        assert params.has_limit
        assert params.limit == 1000
        assert params.has_offset
        assert params.offset == 500

    def test_extract_limit_from_ruby_literal(self):
        """Test extracting LIMIT from Ruby with literal value."""
        code = "Member.limit(1000)"
        params = self.extractor.extract_from_ruby(code)

        assert params.has_limit
        assert params.limit == 1000

    def test_extract_limit_from_ruby_constant(self):
        """Test extracting LIMIT from Ruby with constant."""
        code = "Member.limit(VC_PAGE_SIZE)"
        constants = {"VC_PAGE_SIZE": 1000}
        params = self.extractor.extract_from_ruby(code, constants)

        assert params.has_limit
        assert params.limit == 1000
        assert params.page_size == 1000

    def test_extract_offset_with_page_size(self):
        """Test extracting page size from offset expression."""
        code = "Member.offset((page-1)*1000).limit(1000)"
        params = self.extractor.extract_from_ruby(code)

        assert params.has_offset
        assert params.has_limit
        assert params.page_size == 1000

    def test_extract_offset_with_constant(self):
        """Test extracting offset with constant."""
        code = "Member.offset((page-1)*VC_PAGE_SIZE).limit(VC_PAGE_SIZE)"
        constants = {"VC_PAGE_SIZE": 1000}
        params = self.extractor.extract_from_ruby(code, constants)

        assert params.has_offset
        assert params.has_limit
        assert params.page_size == 1000


class TestPaginationMatcher:
    """Test pagination compatibility checking."""

    def setup_method(self):
        self.matcher = PaginationMatcher()

    def test_perfect_match(self):
        """Test perfect LIMIT/OFFSET match."""
        sql_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, offset=0)
        code_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, page_size=1000)

        result = self.matcher.match(sql_params, code_params)

        assert result.compatibility == CompatibilityLevel.PERFECT
        assert result.limit_match
        assert result.offset_compatible
        assert len(result.issues) == 0

    def test_limit_mismatch(self):
        """Test LIMIT value mismatch."""
        sql_params = PaginationParams(has_limit=True, limit=500)
        code_params = PaginationParams(has_limit=True, limit=1000)

        result = self.matcher.match(sql_params, code_params)

        assert result.compatibility == CompatibilityLevel.INCOMPATIBLE
        assert not result.limit_match
        assert "LIMIT mismatch" in result.issues[0]

    def test_offset_incompatible(self):
        """Test OFFSET that's not a multiple of page size."""
        # SQL wants offset 500, but code uses page_size 1000
        # 500 is not a multiple of 1000, so it's impossible
        sql_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, offset=500)
        code_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, page_size=1000)

        result = self.matcher.match(sql_params, code_params)

        assert result.compatibility == CompatibilityLevel.INCOMPATIBLE
        assert not result.offset_compatible
        assert "OFFSET incompatible" in result.issues[0]
        assert "500 is not a multiple of page_size=1000" in result.issues[0]

    def test_offset_compatible(self):
        """Test OFFSET that IS a multiple of page size."""
        # SQL wants offset 2000, code uses page_size 1000
        # 2000 = 2 * 1000, so it's achievable with page=3
        sql_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, offset=2000)
        code_params = PaginationParams(has_limit=True, limit=1000, has_offset=True, page_size=1000)

        result = self.matcher.match(sql_params, code_params)

        assert result.compatibility in (CompatibilityLevel.PERFECT, CompatibilityLevel.COMPATIBLE)
        assert result.offset_compatible
        assert len(result.issues) == 0


class TestUserReportedPaginationBug:
    """Test the specific pagination issue reported by the user."""

    def setup_method(self):
        self.matcher = PaginationMatcher()
        self.scorer = UnifiedConfidenceScorer()
        self.where_matcher = WhereClauseMatcher()

    def test_offset_500_vs_page_size_1000(self):
        """
        Test the key issue: SQL has OFFSET 500, but code uses page_size 1000.

        This is IMPOSSIBLE - you cannot generate offset=500 with (page-1)*1000.
        """
        sql = """
        SELECT * FROM members
        WHERE company_id = 123
        ORDER BY id ASC
        LIMIT 1000
        OFFSET 500
        """

        code = """
        Member.where(company_id: company.id)
            .order(id: :asc)
            .offset((page-1) * VC_PAGE_SIZE)
            .limit(VC_PAGE_SIZE)
        """

        constants = {"VC_PAGE_SIZE": 1000}

        # Test pagination matching
        pag_result = self.matcher.match_sql_to_code(sql, code, constants)

        assert pag_result.compatibility == CompatibilityLevel.INCOMPATIBLE
        assert not pag_result.offset_compatible
        assert len(pag_result.issues) > 0
        assert "500 is not a multiple of page_size=1000" in pag_result.issues[0]

    def test_offset_1000_is_compatible(self):
        """
        Test that OFFSET 1000 IS compatible with page_size 1000 (page=2).
        """
        sql = """
        SELECT * FROM members
        WHERE company_id = 123
        ORDER BY id ASC
        LIMIT 1000
        OFFSET 1000
        """

        code = """
        Member.where(company_id: company.id)
            .order(id: :asc)
            .offset((page-1) * VC_PAGE_SIZE)
            .limit(VC_PAGE_SIZE)
        """

        constants = {"VC_PAGE_SIZE": 1000}

        pag_result = self.matcher.match_sql_to_code(sql, code, constants)

        assert pag_result.compatibility in (CompatibilityLevel.PERFECT, CompatibilityLevel.COMPATIBLE)
        assert pag_result.offset_compatible
        assert pag_result.limit_match

    def test_integrated_confidence_scoring_with_pagination(self):
        """
        Test that pagination incompatibility reduces confidence score.
        """
        sql = """
        SELECT * FROM members
        WHERE company_id = 123
        ORDER BY id ASC
        LIMIT 1000
        OFFSET 500
        """

        code = """
        Member.where(company_id: company.id)
            .order(id: :asc)
            .offset((page-1) * VC_PAGE_SIZE)
            .limit(VC_PAGE_SIZE)
        """

        constants = {"VC_PAGE_SIZE": 1000}

        # Build WHERE match result (perfect match for this test)
        sql_conditions = [NormalizedCondition("company_id", Operator.EQ, value="123")]
        code_conditions = [NormalizedCondition("company_id", Operator.EQ, value=None)]  # Parameterized
        where_match = MatchResult(
            matched=sql_conditions,
            missing=[],
            extra=[],
            match_percentage=1.0
        )

        # Build clause presence
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

        # Score with pagination validation
        result = self.scorer.score_match(
            where_match,
            clause_presence,
            pattern_distinctiveness=0.7,
            sql=sql,
            code=code,
            constants=constants
        )

        confidence = result["confidence"]

        # Should be capped at 50% due to incompatible pagination
        assert confidence <= 0.50, f"Incompatible pagination should cap at 50%, got {confidence:.2%}"
        assert any("OFFSET incompatible" in str(issue) for issue in result["why"])


class TestPaginationEdgeCases:
    """Test edge cases in pagination matching."""

    def setup_method(self):
        self.matcher = PaginationMatcher()

    def test_no_pagination_in_sql(self):
        """Test when SQL has no LIMIT/OFFSET."""
        sql = "SELECT * FROM members"
        code = "Member.all"

        result = self.matcher.match_sql_to_code(sql, code)

        assert result.compatibility == CompatibilityLevel.PERFECT
        assert len(result.issues) == 0

    def test_limit_only_match(self):
        """Test when only LIMIT is present (no OFFSET)."""
        sql = "SELECT * FROM members LIMIT 10"
        code = "Member.limit(10)"

        result = self.matcher.match_sql_to_code(sql, code)

        assert result.compatibility == CompatibilityLevel.PERFECT
        assert result.limit_match
        assert len(result.issues) == 0

    def test_unknown_constant(self):
        """Test when constant value is unknown."""
        sql = "SELECT * FROM members LIMIT 1000"
        code = "Member.limit(SOME_CONSTANT)"  # No constants dict provided

        result = self.matcher.match_sql_to_code(sql, code)

        # Should be UNKNOWN since we can't resolve SOME_CONSTANT
        assert result.compatibility in (CompatibilityLevel.UNKNOWN, CompatibilityLevel.PERFECT)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
