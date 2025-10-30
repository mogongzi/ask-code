"""
Unified Confidence Scorer - Single canonical scoring system for SQL-to-Rails code matching.

Provides consistent confidence scoring across all search tools based on:
- WHERE clause completeness (strict semantic matching)
- ORDER BY presence
- LIMIT/OFFSET presence
- Pattern distinctiveness

Replaces multiple inconsistent scoring systems with a single authoritative implementation.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .where_clause_matcher import MatchResult, NormalizedCondition
from .pagination_matcher import PaginationMatcher, CompatibilityLevel


@dataclass
class ScoringWeights:
    """Configurable weights for different SQL clause components."""
    where_conditions: float = 0.60  # WHERE clauses are most important
    order_by: float = 0.15
    limit: float = 0.10
    offset: float = 0.10
    pattern_distinctiveness: float = 0.05

    def validate(self):
        """Ensure weights sum to 1.0."""
        total = (self.where_conditions + self.order_by + self.limit +
                self.offset + self.pattern_distinctiveness)
        if abs(total - 1.0) > 0.01:
            raise ValueError(f"Scoring weights must sum to 1.0, got {total}")


@dataclass
class ClausePresence:
    """Tracks which SQL clauses are present in the query and code."""
    sql_has_where: bool = False
    sql_has_order: bool = False
    sql_has_limit: bool = False
    sql_has_offset: bool = False

    code_has_where: bool = False
    code_has_order: bool = False
    code_has_limit: bool = False
    code_has_offset: bool = False


class UnifiedConfidenceScorer:
    """
    Unified confidence scorer for SQL-to-Rails code matching.

    Provides strict semantic matching with accurate confidence scores.
    """

    def __init__(self, weights: Optional[ScoringWeights] = None):
        """
        Initialize scorer with optional custom weights.

        Args:
            weights: Custom scoring weights (uses defaults if not provided)
        """
        self.weights = weights or ScoringWeights()
        self.weights.validate()
        self.pagination_matcher = PaginationMatcher()

    def score_match(
        self,
        where_match_result: MatchResult,
        clause_presence: ClausePresence,
        pattern_distinctiveness: float = 0.5,
        sql_analysis: Optional[Any] = None,
        sql: Optional[str] = None,
        code: Optional[str] = None,
        constants: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Calculate confidence score for a code match.

        Args:
            where_match_result: Result of WHERE clause matching
            clause_presence: Which clauses are present
            pattern_distinctiveness: How distinctive the matched patterns are
            sql_analysis: Optional SQL analysis object
            sql: Optional raw SQL string (for pagination validation)
            code: Optional raw code string (for pagination validation)
            constants: Optional dict of constant values (e.g., {"VC_PAGE_SIZE": 1000})

        Returns:
            Dict with 'confidence' (float 0-1) and 'why' (list of explanations)
        """
        score = 0.0
        why = []

        # 1. Score WHERE clause matching (60% weight, STRICT)
        where_score, where_why = self._score_where_conditions(where_match_result)
        score += where_score * self.weights.where_conditions
        why.extend(where_why)

        # 2. Score ORDER BY presence (15% weight)
        order_score, order_why = self._score_order_by(clause_presence)
        score += order_score * self.weights.order_by
        if order_why:
            why.append(order_why)

        # 3. Score LIMIT presence (10% weight)
        limit_score, limit_why = self._score_limit(clause_presence)
        score += limit_score * self.weights.limit
        if limit_why:
            why.append(limit_why)

        # 4. Score OFFSET presence (10% weight)
        offset_score, offset_why = self._score_offset(clause_presence)
        score += offset_score * self.weights.offset
        if offset_why:
            why.append(offset_why)

        # 5. Score pattern distinctiveness (5% weight)
        pattern_score = pattern_distinctiveness
        score += pattern_score * self.weights.pattern_distinctiveness

        # 6. Validate pagination values if SQL and code are provided
        pagination_match = None
        if sql and code:
            pagination_match = self.pagination_matcher.match_sql_to_code(sql, code, constants)
            if pagination_match.issues:
                why.extend([f"⚠ {issue}" for issue in pagination_match.issues])

        # Apply strict penalties for missing critical clauses and incompatible pagination
        score = self._apply_strict_penalties(score, where_match_result, clause_presence, pagination_match, why)

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        return {
            "confidence": score,
            "why": why,
            "details": {
                "where_score": where_score,
                "order_score": order_score,
                "limit_score": limit_score,
                "offset_score": offset_score,
                "pattern_score": pattern_score,
                "pagination_compatibility": pagination_match.compatibility.value if pagination_match else None
            }
        }

    def _score_where_conditions(self, match_result: MatchResult) -> tuple[float, List[str]]:
        """
        Score WHERE clause matching with STRICT semantic validation.

        Returns (score, explanations)
        """
        why = []

        # No WHERE conditions in SQL = perfect match
        if len(match_result.matched) == 0 and len(match_result.missing) == 0:
            return 1.0, ["✓ No WHERE conditions required"]

        # All conditions matched = perfect WHERE score
        if match_result.is_complete_match:
            why.append(f"✓ All {len(match_result.matched)} WHERE conditions matched")

            # Extra conditions are OK (code might be more specific)
            if match_result.extra:
                why.append(f"  Note: {len(match_result.extra)} additional conditions in code")

            return 1.0, why

        # Partial match: STRICT penalties
        matched_count = len(match_result.matched)
        missing_count = len(match_result.missing)
        total_required = matched_count + missing_count

        if missing_count > 0:
            why.append(f"✗ Missing {missing_count}/{total_required} WHERE conditions:")
            for cond in match_result.missing:
                why.append(f"    - {cond}")

        # Strict scoring: Each missing condition significantly reduces score
        # With 1 missing out of 4: 3/4 = 0.75, but we penalize to max 0.4
        base_match_ratio = match_result.match_percentage

        if base_match_ratio >= 0.75:
            # 75-100%: Allow 0.5-0.7 range
            score = 0.5 + (base_match_ratio - 0.75) * 0.8
        elif base_match_ratio >= 0.5:
            # 50-75%: Allow 0.3-0.5 range
            score = 0.3 + (base_match_ratio - 0.5) * 0.8
        else:
            # Below 50%: Linear scale from 0-0.3
            score = base_match_ratio * 0.6

        return score, why

    def _score_order_by(self, clause_presence: ClausePresence) -> tuple[float, Optional[str]]:
        """Score ORDER BY clause presence."""
        if not clause_presence.sql_has_order:
            # No ORDER BY required
            return 1.0, None

        if clause_presence.code_has_order:
            return 1.0, "✓ ORDER BY present"

        return 0.0, "✗ Missing ORDER BY clause"

    def _score_limit(self, clause_presence: ClausePresence) -> tuple[float, Optional[str]]:
        """Score LIMIT clause presence."""
        if not clause_presence.sql_has_limit:
            return 1.0, None

        if clause_presence.code_has_limit:
            return 1.0, "✓ LIMIT present"

        return 0.0, "✗ Missing LIMIT clause"

    def _score_offset(self, clause_presence: ClausePresence) -> tuple[float, Optional[str]]:
        """Score OFFSET clause presence."""
        if not clause_presence.sql_has_offset:
            return 1.0, None

        if clause_presence.code_has_offset:
            return 1.0, "✓ OFFSET present"

        return 0.0, "✗ Missing OFFSET clause"

    def _apply_strict_penalties(
        self,
        base_score: float,
        where_match_result: MatchResult,
        clause_presence: ClausePresence,
        pagination_match: Optional[Any],
        why: List[str]
    ) -> float:
        """
        Apply strict penalties for critical mismatches.

        In strict mode:
        - Any missing WHERE condition caps score at 40%
        - Missing ORDER BY when pagination present (LIMIT/OFFSET) caps at 60%
        - Mismatched operators (IS NULL vs IS NOT NULL) = 0% for that condition
        - Incompatible pagination values (LIMIT/OFFSET) caps at 50%
        """
        score = base_score

        # Penalty 1: Missing ANY WHERE condition caps score at 40%
        if where_match_result.missing:
            score = min(score, 0.40)
            why.append("⚠ Missing WHERE conditions cap confidence at 40%")

        # Penalty 2: Pagination without ORDER BY is dangerous (nondeterministic)
        if (clause_presence.sql_has_limit or clause_presence.sql_has_offset):
            if clause_presence.sql_has_order and not clause_presence.code_has_order:
                score = min(score, 0.60)
                why.append("⚠ Missing ORDER BY with pagination caps confidence at 60%")

        # Penalty 3: Incompatible pagination values
        if pagination_match and pagination_match.compatibility == CompatibilityLevel.INCOMPATIBLE:
            score = min(score, 0.50)
            why.append("⚠ Incompatible LIMIT/OFFSET values cap confidence at 50%")

        # Penalty 4: Missing multiple critical clauses
        missing_critical_count = 0
        if where_match_result.missing:
            missing_critical_count += len(where_match_result.missing)
        if clause_presence.sql_has_order and not clause_presence.code_has_order:
            missing_critical_count += 1
        if clause_presence.sql_has_limit and not clause_presence.code_has_limit:
            missing_critical_count += 1

        if missing_critical_count >= 3:
            score = min(score, 0.25)
            why.append("⚠ Multiple missing clauses cap confidence at 25%")

        return score

    def create_clause_presence(
        self,
        sql_analysis: Any,
        code_snippet: str
    ) -> ClausePresence:
        """
        Helper method to create ClausePresence from sql_analysis and code.

        Args:
            sql_analysis: SemanticSQLAnalyzer result
            code_snippet: Ruby/Rails code string

        Returns:
            ClausePresence object
        """
        presence = ClausePresence()

        # SQL clause presence (from analysis)
        presence.sql_has_where = len(getattr(sql_analysis, "where_conditions", [])) > 0
        presence.sql_has_order = getattr(sql_analysis, "has_order", False)
        presence.sql_has_limit = getattr(sql_analysis, "has_limit", False)
        presence.sql_has_offset = getattr(sql_analysis, "has_offset", False)

        # Code clause presence (from snippet)
        code_lower = code_snippet.lower()
        presence.code_has_where = ".where(" in code_lower
        presence.code_has_order = ".order(" in code_lower
        presence.code_has_limit = ".limit(" in code_lower
        presence.code_has_offset = ".offset(" in code_lower

        return presence


# Convenience function for backward compatibility
def calculate_confidence(
    where_match_result: MatchResult,
    clause_presence: ClausePresence,
    pattern_distinctiveness: float = 0.5,
    sql_analysis: Optional[Any] = None
) -> float:
    """
    Calculate confidence score (simplified interface).

    Returns just the confidence value (0.0-1.0).
    """
    scorer = UnifiedConfidenceScorer()
    result = scorer.score_match(
        where_match_result,
        clause_presence,
        pattern_distinctiveness,
        sql_analysis
    )
    return result["confidence"]
