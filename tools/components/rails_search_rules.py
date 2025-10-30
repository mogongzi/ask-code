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
    optional: bool = False  # If True, pattern enhances matches but doesn't exclude files


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
        1. Search for .limit( and .offset( methods (structural patterns)
        2. Search for .take, .first, .last (LIMIT equivalents)
        3. Search for pagination helpers

        Note: We use structural patterns (e.g., .limit()) instead of literal values
        (e.g., .limit(500)) because values often come from constants, variables, or config.
        """
        patterns = []

        # Combined LIMIT pattern: .limit(), .take, .first, .last (all LIMIT equivalents)
        # Using a single pattern ensures file-level filtering accepts any of these methods
        patterns.append(SearchPattern(
            pattern=r"\.(?:limit\(|take\b|first\b|last\b)",
            distinctiveness=0.6,  # Moderately distinctive
            description=".limit()/.take/.first/.last method call",
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

        REQUIRED:
        - Model name MUST be present in the content

        High confidence if:
        - Has .limit() or .take/.first/.last present (structural match)
        - Has both .limit() and .offset() when SQL has both
        - Has ORDER BY when SQL has ORDER BY

        Note: We check for structural patterns, not literal values, because
        values often come from constants, variables, or configuration.
        """
        content = match.get("content", "").lower()

        # REQUIRE model name to be present - reject if wrong model
        if sql_analysis.primary_model:
            model_lower = sql_analysis.primary_model.lower()
            if model_lower not in content:
                return 0.0  # REJECT - wrong model or no model reference

        confidence = 0.6  # Base confidence (model name is present)

        # Check for .limit( or .take/.first/.last presence (structural check)
        has_limit_equivalent = (
            ".limit(" in content or
            ".take" in content or
            ".first" in content or
            ".last" in content
        )
        if has_limit_equivalent:
            confidence += 0.2

        # Check OFFSET presence
        if sql_analysis.has_offset:
            if ".offset(" in content:
                confidence += 0.2
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

    NOTE: This rule provides FALLBACK patterns only. The primary scope matching
    is now done semantically by ModelScopeAnalyzer + SQLToScopeMatcher at the
    engine level, which:
    - Reads the actual model file
    - Extracts ALL scopes (no hardcoded names)
    - Matches SQL WHERE clauses to scopes semantically
    - Generates targeted search patterns based on matched scopes

    This rule's patterns are used when:
    - Model file doesn't exist
    - No scopes are defined in the model
    - No semantic match is found (confidence < 0.8)

    Domain knowledge (for fallback patterns):
    - WHERE conditions often defined as scopes in models
    - Scope chains: Model.scope1.scope2.limit
    - Generic scope usage patterns
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/models/**/*.rb", "Model definitions (scopes and constants)", 1),
            SearchLocation("lib/**/*.rb", "Lib helpers (scope chain usage)", 2),
            SearchLocation("app/mailers/**/*.rb", "Mailers (scope chain usage)", 3),
            SearchLocation("app/controllers/**/*.rb", "Controllers (scope chain usage)", 4),
            SearchLocation("app/jobs/**/*.rb", "Jobs (scope chain usage)", 5),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build scope/constant search patterns.

        Strategy:
        1. Search for Model name with method chains (structural, not specific scope names)
        2. Search for generic scope keyword (for scope definitions)
        3. Search for common constant patterns (COND, CONDITION)

        Note: We avoid hardcoding specific scope names or prefixes because:
        - Rails apps have infinite possible scope names based on business logic
        - Scope names often don't match SQL column names
        - We can't predict custom naming conventions
        """
        patterns = []

        # === Structural patterns for Model method chains ===
        if sql_analysis.primary_model:
            # Generic scope chain: Model.anything.anything.limit/take/first/last
            # This catches ALL scope chains without assuming specific scope names
            if getattr(sql_analysis, "has_limit", False):
                patterns.append(SearchPattern(
                    pattern=rf"{sql_analysis.primary_model}\.\w+.*\.(?:limit|take|first|last)\b",
                    distinctiveness=0.65,
                    description=f"{sql_analysis.primary_model} scope chain with .limit/.take/.first/.last",
                    clause_type="scope_chain"
                ))

            # Generic scope chain: Model.anything.anything.offset
            if getattr(sql_analysis, "has_offset", False):
                patterns.append(SearchPattern(
                    pattern=rf"{sql_analysis.primary_model}\.\w+.*\.offset\(",
                    distinctiveness=0.7,
                    description=f"{sql_analysis.primary_model} scope chain with .offset",
                    clause_type="scope_chain"
                ))

            # Generic: Model name followed by method call (very broad)
            patterns.append(SearchPattern(
                pattern=rf"{sql_analysis.primary_model}\.\w+",
                distinctiveness=0.4,
                description=f"{sql_analysis.primary_model} method call",
                clause_type="model_usage"
            ))

        # Search for generic scope definitions (not column-specific)
        # This finds ANY scope definition in model files
        # OPTIONAL: Only applies to app/models/, not lib/ or other directories
        patterns.append(SearchPattern(
            pattern=r"scope\s+:",
            distinctiveness=0.5,
            description="Scope definition (generic)",
            clause_type="scope_definition",
            optional=True  # Don't exclude non-model files that lack scope definitions
        ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate scope/constant match.

        REQUIRED:
        - Model name MUST be present in the content

        High confidence if:
        - Query chain structure matches (has .limit, .offset, .order as expected)
        - Is a scope definition or scope chain usage

        Note: We use structural validation, not column name matching, because:
        - Column names in SQL rarely match scope names in Ruby
        - Scope abstractions hide SQL details
        - We can't reliably extract columns from scopes without AST parsing
        """
        import re

        content = match.get("content", "").lower()

        # REQUIRE model name to be present - reject if wrong model
        if sql_analysis.primary_model:
            model_lower = sql_analysis.primary_model.lower()
            if model_lower not in content:
                return 0.0  # REJECT - wrong model or no model reference

        confidence = 0.6  # Base confidence (model name is present)

        # Check for query chain structure matching SQL
        if getattr(sql_analysis, "has_limit", False):
            has_limit_equivalent = (
                ".limit(" in content or
                ".take" in content or
                ".first" in content or
                ".last" in content
            )
            if has_limit_equivalent:
                confidence += 0.15

        if getattr(sql_analysis, "has_offset", False):
            if ".offset(" in content:
                confidence += 0.15
            else:
                confidence -= 0.1  # Missing expected clause

        if getattr(sql_analysis, "has_order", False):
            if ".order(" in content:
                confidence += 0.1

        # Bonus for scope definitions (in model files)
        if "scope" in content:
            confidence += 0.1

        return min(1.0, max(0.0, confidence))


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
            SearchLocation("lib/**/*.rb", "Lib helpers (association usage)", 2),
            SearchLocation("app/controllers/**/*.rb", "Association usage in controllers", 3),
            SearchLocation("app/mailers/**/*.rb", "Association usage in mailers", 4),
            SearchLocation("app/jobs/**/*.rb", "Association usage in jobs", 5),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build association search patterns.

        Strategy:
        1. Search for generic method chains with .limit/.offset
        2. Search for has_many/belongs_to declarations (structural)

        Note: We avoid hardcoding specific wrapper method prefixes because:
        - Rails apps use infinite naming conventions
        - Association methods vary by business domain
        - We can't predict custom method names
        """
        patterns = []

        # Generic method call chain with limit - catches association wrappers
        # without assuming specific prefixes
        if getattr(sql_analysis, "has_limit", False):
            patterns.append(SearchPattern(
                pattern=r"\.\w+.*\.limit\(",
                distinctiveness=0.5,
                description="Method call chain with .limit",
                clause_type="method_chain"
            ))

        # Generic method call chain with offset
        if getattr(sql_analysis, "has_offset", False):
            patterns.append(SearchPattern(
                pattern=r"\.\w+.*\.offset\(",
                distinctiveness=0.6,
                description="Method call chain with .offset",
                clause_type="method_chain"
            ))

        # Search for association declarations (structural pattern)
        # This finds has_many, belongs_to, has_one, etc. in model files
        patterns.append(SearchPattern(
            pattern=r"(has_many|belongs_to|has_one)\s+:",
            distinctiveness=0.5,
            description="Association declaration",
            clause_type="association_declaration"
        ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate association match.

        REQUIRED:
        - Model name MUST be present in the content

        Note: We use structural validation (presence of method chains, associations)
        rather than checking for specific foreign key names or association names,
        because these vary greatly across applications.
        """
        content = match.get("content", "").lower()

        # REQUIRE model name to be present - reject if wrong model
        if sql_analysis.primary_model:
            model_lower = sql_analysis.primary_model.lower()
            if model_lower not in content:
                return 0.0  # REJECT - wrong model or no model reference

        confidence = 0.6  # Base confidence (model name is present)

        # Check for method chain structure matching SQL
        if getattr(sql_analysis, "has_limit", False):
            has_limit_equivalent = (
                ".limit(" in content or
                ".take" in content or
                ".first" in content or
                ".last" in content
            )
            if has_limit_equivalent:
                confidence += 0.2

        if getattr(sql_analysis, "has_offset", False):
            if ".offset(" in content:
                confidence += 0.2

        # Bonus for association declarations
        if any(keyword in content for keyword in ["has_many", "belongs_to", "has_one"]):
            confidence += 0.1

        return min(1.0, max(0.0, confidence))


class OrderByRule(RailsSearchRule):
    """ORDER BY clauses → Sorting contexts.

    Domain knowledge:
    - ORDER BY with specific column is moderately distinctive
    - Often combined with LIMIT for pagination
    - Common patterns: ORDER BY id ASC, ORDER BY created_at DESC
    """

    def get_search_locations(self) -> List[SearchLocation]:
        return [
            SearchLocation("app/models/**/*.rb", "Model code", 1),
            SearchLocation("lib/**/*.rb", "Lib helpers", 2),
            SearchLocation("app/controllers/**/*.rb", "Controller code", 3),
            SearchLocation("app/mailers/**/*.rb", "Mailer code", 4),
            SearchLocation("app/jobs/**/*.rb", "Job code", 5),
        ]

    def build_search_patterns(self, sql_analysis: Any) -> List[SearchPattern]:
        """Build ORDER BY search patterns.

        Note: We use structural patterns (e.g., .order()) instead of literal column names
        (e.g., .order(created_at)) because column names might be in variables, dynamic sorting,
        or Arel expressions.
        """
        patterns = []

        # Generic .order( pattern - structural, not column-specific
        patterns.append(SearchPattern(
            pattern=r"\.order\(",
            distinctiveness=0.5,
            description=".order() method call",
            clause_type="order"
        ))

        return patterns

    def validate_match(self, match: Dict[str, Any], sql_analysis: Any) -> float:
        """Validate ORDER BY match.

        REQUIRED:
        - Model name MUST be present in the content

        Note: We check for structural patterns (.order( present), not literal column names,
        because column names might come from variables, dynamic sorting, or Arel expressions.
        """
        content = match.get("content", "").lower()

        # REQUIRE model name to be present - reject if wrong model
        if sql_analysis.primary_model:
            model_lower = sql_analysis.primary_model.lower()
            if model_lower not in content:
                return 0.0  # REJECT - wrong model or no model reference

        confidence = 0.6  # Base confidence (model name is present)

        # Check for .order( presence (structural check)
        if ".order(" in content:
            confidence += 0.2

            # Bonus if also has .limit or .take/.first/.last (common pagination pattern)
            has_limit_equivalent = (
                ".limit(" in content or
                ".take" in content or
                ".first" in content or
                ".last" in content
            )
            if has_limit_equivalent:
                confidence += 0.1

        return min(1.0, max(0.0, confidence))

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
