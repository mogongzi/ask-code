from __future__ import annotations

from typing import List, Any


class ResultRanker:
    """Ranks matches by confidence and type, removing duplicates."""

    def rank(self, matches: List[Any], analysis: Any) -> List[Any]:
        # Remove duplicates based on path and line
        seen = set()
        unique_matches: List[Any] = []

        for match in matches:
            key = (getattr(match, 'path', None), getattr(match, 'line', None))
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)

        def confidence_score(match: Any) -> int:
            conf = getattr(match, 'confidence', '') or ''
            conf_lower = conf.lower()
            if 'high' in conf_lower:
                return 3
            if 'medium' in conf_lower:
                return 2
            return 1

        def type_score(match: Any) -> int:
            mtype = getattr(match, 'match_type', '')
            return 2 if mtype == 'definition' else 1

        return sorted(unique_matches, key=lambda m: (confidence_score(m), type_score(m)), reverse=True)

