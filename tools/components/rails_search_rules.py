"""
Domain-Aware Rails Search Rules

Encodes Rails conventions as class-based rules that guide SQL-to-code search:
- WHERE clauses → Model scopes and constants
- LIMIT/OFFSET → Pagination contexts (mailers, jobs, controllers)
- ORDER BY → Sorting contexts
- Associations → Association wrappers and foreign keys

Each rule knows:
1. Where to search (file patterns)
2. What to search for (pattern builders)
3. How to validate matches (confidence scoring)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class SearchPattern:
    """A search pattern with metadata for progressive refinement."""
    pattern: str
    distinctiveness: float  # 0.0 (very common) to 1.0 (very rare)
    description: str
    clause_type: str  # "limit", "where", "order", "association", etc.


@dataclass
class SearchLocation:
    """Where to search in the Rails project."""
    glob_pattern: str  # e.g., "app/models/**/*.rb"
    description: str
    priority: int  # Lower = search first


class RailsSearchRule(ABC):
    """Base class for domain-aware Rails search rules."""

    @abstractmethod
    def get_search_locations(self) -> List[SearchLocation]:
        """Return locations to search, ordered by priority."""
        pass

    @abstractmethod
    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build search patterns from SQL analysis, ranked by distinctiveness."""
        pass

    @abstractmethod
    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate a match and return confidence score (0.0 to 1.0)."""
        pass


class LimitOffsetRule(RailsSearchRule):
    """LIMIT/OFFSET clauses → Pagination contexts.

    Domain knowledge:
    - LIMIT with specific value is VERY distinctive (e.g., LIMIT 500)
    - Found in: mailers (batch processing), jobs (background tasks),
      controllers with custom pagination
    - Often combined with OFFSET and ORDER BY for stable pagination
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/mailers/**/*.rb", "Mailers (batch email processing)", 1),
            SearchLocation("lib/**/*.rb", "Lib helpers (batch utilities)", 2),
            SearchLocation("app/jobs/**/*.rb", "Background jobs", 3),
            SearchLocation("app/controllers/**/*.rb", "Controllers with custom pagination", 4),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build LIMIT/OFFSET search patterns.

        Strategy:
        1. Search for exact LIMIT value (e.g., "500") - VERY distinctive
        2. Search for .limit( and .offset( methods
        3. Search for pagination helpers
        """
        patterns = []

        # Extract LIMIT value from SQL
        limit_value = self._extract_limit_value(sql_analysis)
        if limit_value:
            # Exact limit value is VERY distinctive (few files use same limit)
            patterns.append(SearchPattern(
                pattern=str(limit_value),
                distinctiveness=0.9,  # Very rare
                description=f"Exact LIMIT value: {limit_value}",
                clause_type="limit"
            ))

            # Also search for .limit(VALUE) pattern
            patterns.append(SearchPattern(
                pattern=rf"\.limit\({limit_value}\)",
                distinctiveness=0.85,
                description=f".limit({limit_value}) method call",
                clause_type="limit"
            ))

        # Generic .limit( pattern (less distinctive)
        patterns.append(SearchPattern(
            pattern=r"\.limit\(",
            distinctiveness=0.5,
            description=".limit() method call (generic)",
            clause_type="limit"
        ))

        # OFFSET patterns
        if sql_analysis.has_offset:
            patterns.append(SearchPattern(
                pattern=r"\.offset\(",
                distinctiveness=0.7,  # More rare than .limit
                description=".offset() method call",
                clause_type="offset"
            ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate LIMIT/OFFSET match.

        High confidence if:
        - Has both .limit() and .offset() when SQL has both
        - Has correct LIMIT value
        - Has ORDER BY when SQL has ORDER BY
        """
        content = match.get("content", "").lower()
        confidence = 0.5  # Base confidence

        # Check LIMIT value
        limit_value = self._extract_limit_value(sql_analysis)
        if limit_value and str(limit_value) in content:
            confidence += 0.3

        # Check OFFSET presence
        if sql_analysis.has_offset:
            if ".offset(" in content:
                confidence += 0.1
            else:
                confidence -= 0.2  # Missing expected clause

        # Check ORDER BY presence
        if sql_analysis.has_order:
            if ".order(" in content:
                confidence += 0.1
            else:
                confidence -= 0.1

        return min(1.0, max(0.0, confidence))

    def _extract_limit_value(self, sql_analysis: Any) -> Optional[int]:
        """Extract LIMIT value from SQL analysis."""
        import re
        raw_sql = getattr(sql_analysis, "raw_sql", "")
        match = re.search(r"\bLIMIT\s+(\d+)", raw_sql, re.IGNORECASE)
        return int(match.group(1)) if match else None


class ScopeDefinitionRule(RailsSearchRule):
    """WHERE clauses → Model scopes and constants.

    Domain knowledge:
    - WHERE conditions often defined as scopes in models
    - Constants like CANONICAL_COND, ACTIVE_COND combine multiple WHERE clauses
    - Scope chains: .active → .not_disabled → .all_canonical
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/models/**/*.rb", "Model definitions (scopes and constants)", 1),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build scope/constant search patterns.

        Strategy:
        1. Search for column names in scope definitions
        2. Search for constant names (e.g., CANONICAL_COND, ACTIVE_COND)
        3. Search for scope names inferred from WHERE conditions
        """
        patterns = []

        # Extract WHERE condition columns
        where_columns = [
            cond.column.name
            for cond in getattr(sql_analysis, "where_conditions", [])
        ]

        # Search for constants that might combine multiple WHERE conditions
        # Pattern: Multiple columns in same constant = distinctive
        if len(where_columns) >= 2:
            # Search for lines with multiple column names (likely a constant)
            # This is distinctive because constants bundle multiple conditions
            patterns.append(SearchPattern(
                pattern=rf"(COND|CONDITION)",  # Common constant naming
                distinctiveness=0.8,
                description="Constant definitions (COND, CONDITION)",
                clause_type="where_constant"
            ))

        # Search for scope definitions with specific columns
        for col in where_columns:
            # Handle both: scope :name, -> { ... } and scope(:name, lambda do ... end)
            # Also match if column name appears in the scope name (e.g., for_custom_domain)
            # Pattern explanation:
            # - scope\s* : 'scope' followed by optional whitespace
            # - (?:[:(])? : optionally followed by : or ( (non-capturing)
            # - \s* : optional whitespace
            # - :\w* : colon followed by optional word chars (scope name prefix)
            # - {col} : the column name we're looking for
            patterns.append(SearchPattern(
                pattern=rf"scope\s*(?:[:(])?\s*:\w*{col}",
                distinctiveness=0.6,
                description=f"Scope definition filtering by {col}",
                clause_type="where_scope"
            ))

        # Search for scope usage patterns - infer likely scope names from WHERE columns
        if sql_analysis.primary_model and where_columns:
            # Infer likely scope names from column names
            # Example: custom_domain column → likely scope: for_custom_domain
            for col in where_columns:
                # Common Rails scope naming patterns:
                # - for_<column>
                # - by_<column>
                # - with_<column>
                scope_name_patterns = [
                    f"for_{col}",
                    f"by_{col}",
                    f"with_{col}",
                ]

                for scope_name in scope_name_patterns:
                    patterns.append(SearchPattern(
                        pattern=rf"{sql_analysis.primary_model}\.{scope_name}\(",
                        distinctiveness=0.7,  # Higher distinctiveness for specific scope calls
                        description=f"{sql_analysis.primary_model}.{scope_name}() scope call",
                        clause_type="where_scope_usage"
                    ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate scope/constant match.

        High confidence if match contains the EXACT WHERE condition columns.
        Heavily penalize if code has EXTRA columns not in SQL (different query).
        Filter out false positives (generic ActiveRecord methods, column references).
        """
        import re

        content = match.get("content", "").lower()
        pattern_type = match.get("pattern_type", "")

        # Filter out generic ActiveRecord method calls (not scope usage)
        if pattern_type == "where_scope_usage":
            generic_methods = [
                r'\.find_by\(',
                r'\.find_or_create_by\(',
                r'\.where\(',
                r'\.find\(',
                r'\.create\(',
                r'\.update\(',
                r'\.destroy\(',
                r'\.find_from_param\(',
                r'has_many\s+:',
                r'has_one\s+:',
                r'belongs_to\s+:'
            ]

            for generic_pattern in generic_methods:
                if re.search(generic_pattern, content, re.IGNORECASE):
                    # This is a generic ActiveRecord call, not a scope usage
                    return 0.0  # Reject this match

        # Filter out column-only references (e.g., custom_domain: in hash syntax)
        where_columns = [
            cond.column.name.lower()
            for cond in getattr(sql_analysis, "where_conditions", [])
        ]

        # Check if this is just a column reference in hash syntax (key: value)
        if where_columns:
            for col in where_columns:
                # Pattern: column_name: (hash key syntax)
                if re.search(rf'\b{col}\s*:', content):
                    # Check if this is NOT part of a scope definition
                    if not re.search(r'\bscope\b', content, re.IGNORECASE):
                        # This is just a column reference, not a scope call
                        # Still give some score if it's a valid usage, but lower
                        pass  # Continue with normal scoring

        if not where_columns:
            return 0.5

        # Count how many SQL WHERE columns appear in the code
        matched_columns = sum(1 for col in where_columns if col in content)

        # Base confidence from SQL columns present in code
        confidence = matched_columns / len(where_columns)

        # Check for EXTRA columns in code that aren't in SQL
        # Extract columns from common Rails patterns:
        # - where(column: value)
        # - find_by(column: value, column2: value)
        # - scope with where conditions
        code_column_patterns = [
            r'where\s*\(\s*(\w+):',           # where(column:
            r'find_by\s*\(\s*(\w+):',         # find_by(column:
            r'(\w+)\s*:\s*[\w\.\[\]$]+',      # column: value (broader match)
        ]

        code_columns = set()
        for pattern in code_column_patterns:
            matches = re.findall(pattern, content)
            code_columns.update(m for m in matches if m not in ['lambda', 'do', 'end'])

        # If we found explicit column references in code, check for extras
        if code_columns:
            sql_column_set = set(where_columns)
            extra_columns = code_columns - sql_column_set

            if extra_columns:
                # Code has WHERE conditions not in SQL = DIFFERENT QUERY
                # Apply severe penalty (this is likely a false positive)
                penalty = 0.3  # Reduce confidence to 30% or less
                confidence *= penalty

        return confidence


class AssociationRule(RailsSearchRule):
    """Foreign keys → Association wrappers.

    Domain knowledge:
    - Foreign keys (company_id) often accessed via associations
    - Association wrappers: company.find_all_active instead of Member.where(company_id: X)
    - These wrappers add implicit WHERE clauses for tenant filtering
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/models/**/*.rb", "Association wrappers in models", 1),
            SearchLocation("app/controllers/**/*.rb", "Association usage in controllers", 2),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build association search patterns.

        Strategy:
        1. Extract foreign keys from WHERE conditions
        2. Search for association wrapper methods (e.g., find_all_active)
        3. Search for association usage patterns
        """
        patterns = []

        # Extract foreign keys
        foreign_keys = [
            cond.column
            for cond in getattr(sql_analysis, "where_conditions", [])
            if cond.column.is_foreign_key
        ]

        for fk in foreign_keys:
            assoc_name = fk.association_name

            # Search for association wrapper methods
            patterns.append(SearchPattern(
                pattern=rf"def\s+find_\w+",
                distinctiveness=0.7,
                description=f"Association wrapper method (find_*)",
                clause_type="association_wrapper"
            ))

            # Search for association usage
            patterns.append(SearchPattern(
                pattern=rf"\.{assoc_name}\.",
                distinctiveness=0.5,
                description=f"Association usage: .{assoc_name}.",
                clause_type="association_usage"
            ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate association match."""
        # Base confidence for association matches
        return 0.6


class OrderByRule(RailsSearchRule):
    """ORDER BY clauses → Sorting contexts.

    Domain knowledge:
    - ORDER BY with specific column is moderately distinctive
    - Often combined with LIMIT for pagination
    - Common patterns: ORDER BY id ASC, ORDER BY created_at DESC
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/**/*.rb", "All application code", 1),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build ORDER BY search patterns."""
        patterns = []

        # Extract ORDER BY column
        order_column = self._extract_order_column(sql_analysis)
        if order_column:
            # Search for .order(column: :asc/:desc)
            patterns.append(SearchPattern(
                pattern=rf"\.order\([:\'\"]?{order_column}",
                distinctiveness=0.6,
                description=f".order({order_column}) method call",
                clause_type="order"
            ))

        # Generic .order( pattern
        patterns.append(SearchPattern(
            pattern=r"\.order\(",
            distinctiveness=0.4,
            description=".order() method call (generic)",
            clause_type="order"
        ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate ORDER BY match."""
        content = match.get("content", "").lower()

        order_column = self._extract_order_column(sql_analysis)
        if order_column and order_column.lower() in content:
            return 0.8

        return 0.5

    def _extract_order_column(self, sql_analysis: Any) -> Optional[str]:
        """Extract ORDER BY column from SQL analysis."""
        import re
        raw_sql = getattr(sql_analysis, "raw_sql", "")
        match = re.search(r"\bORDER\s+BY\s+[\w.]+\.?(\w+)", raw_sql, re.IGNORECASE)
        return match.group(1) if match else None


class RailsSearchRuleSet:
    """Collection of all domain-aware search rules."""

    def __init__(self):
        self.rules = [
            LimitOffsetRule(),
            ScopeDefinitionRule(),
            AssociationRule(),
            OrderByRule(),
        ]

    def get_all_rules(self) -> List[RailsSearchRule]:
        """Get all available rules."""
        return self.rules

    def get_applicable_rules(self, sql_analysis: Any) -> List[RailsSearchRule]:
        """Get rules applicable to the given SQL analysis.

        Filters rules based on SQL characteristics:
        - Has LIMIT/OFFSET → LimitOffsetRule
        - Has WHERE → ScopeDefinitionRule
        - Has foreign keys → AssociationRule
        - Has ORDER BY → OrderByRule
        """
        applicable = []

        # Always include scope rule if there are WHERE conditions
        if getattr(sql_analysis, "where_conditions", []):
            applicable.append(ScopeDefinitionRule())

        # Include LIMIT/OFFSET rule if SQL has LIMIT
        if getattr(sql_analysis, "has_limit", False):
            applicable.append(LimitOffsetRule())

        # Include association rule if there are foreign keys
        where_conditions = getattr(sql_analysis, "where_conditions", [])
        if any(cond.column.is_foreign_key for cond in where_conditions):
            applicable.append(AssociationRule())

        # Include ORDER BY rule if SQL has ORDER BY
        if getattr(sql_analysis, "has_order", False):
            applicable.append(OrderByRule())

        return applicable
