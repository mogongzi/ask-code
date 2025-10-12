from __future__ import annotations

from typing import List

from tools.semantic_sql_analyzer import QueryAnalysis


class RailsPatternMatcher:
    """Adapter to expose Rails pattern suggestions from a QueryAnalysis.

    For now, it returns the patterns inferred by SemanticSQLAnalyzer. This class
    exists to allow future extension without changing callers.
    """

    def patterns_for(self, analysis: QueryAnalysis) -> List[str]:
        return analysis.rails_patterns or []

