"""
WHERE Clause Matcher - Semantic WHERE clause comparison for SQL-to-Rails code matching.

Provides strict semantic matching of WHERE conditions, validating:
- Column names
- Operators (IS NULL, IS NOT NULL, =, !=, <, >, LIKE, IN, etc.)
- Values (for literal comparisons)
- Rails scopes (e.g., Member.active resolves to its WHERE conditions)

Used by confidence scoring to eliminate false positives from substring matching.
"""
from __future__ import annotations

import re
import sqlglot
from sqlglot import exp
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from .rails_inflection import singularize
from .custom_finder_detector import CustomFinderDetector


class Operator(Enum):
    """Normalized SQL operators for semantic comparison."""
    EQ = "="
    NEQ = "!="
    LT = "<"
    LTE = "<="
    GT = ">"
    GTE = ">="
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    LIKE = "LIKE"
    NOT_LIKE = "NOT LIKE"
    IN = "IN"
    NOT_IN = "NOT IN"
    BETWEEN = "BETWEEN"
    UNKNOWN = "UNKNOWN"

    @classmethod
    def from_sqlglot(cls, sqlglot_op: str) -> 'Operator':
        """Convert sqlglot operator key to normalized Operator."""
        mapping = {
            "EQ": cls.EQ,
            "NEQ": cls.NEQ,
            "LT": cls.LT,
            "LTE": cls.LTE,
            "GT": cls.GT,
            "GTE": cls.GTE,
            "IS": cls.IS_NULL,  # Will be refined based on value
            "LIKE": cls.LIKE,
            "NOT_LIKE": cls.NOT_LIKE,
            "IN": cls.IN,
            "NOT_IN": cls.NOT_IN,
            "BETWEEN": cls.BETWEEN,
        }
        return mapping.get(sqlglot_op.upper(), cls.UNKNOWN)

    @classmethod
    def from_ruby_pattern(cls, pattern: str) -> 'Operator':
        """Extract operator from Ruby WHERE clause pattern."""
        pattern_lower = pattern.lower().strip()

        # IS NOT NULL patterns
        if "is not null" in pattern_lower or "not null" in pattern_lower:
            return cls.IS_NOT_NULL

        # IS NULL patterns
        if "is null" in pattern_lower:
            return cls.IS_NULL

        # Inequality patterns
        if "!=" in pattern or "<>" in pattern:
            return cls.NEQ

        # Comparison operators
        if ">=" in pattern:
            return cls.GTE
        if "<=" in pattern:
            return cls.LTE
        if ">" in pattern:
            return cls.GT
        if "<" in pattern:
            return cls.LT

        # LIKE patterns
        if " like " in pattern_lower or ".like(" in pattern_lower:
            return cls.LIKE

        # IN patterns
        if " in " in pattern_lower or ".in(" in pattern_lower:
            return cls.IN

        # Default to equality
        if "=" in pattern:
            return cls.EQ

        return cls.UNKNOWN


@dataclass
class NormalizedCondition:
    """A normalized WHERE condition for semantic comparison."""
    column: str  # Normalized column name (lowercase, no table prefix)
    operator: Operator
    value: Optional[Any] = None
    raw_pattern: str = ""  # Original pattern for debugging

    def matches(self, other: 'NormalizedCondition') -> bool:
        """Check if this condition semantically matches another."""
        # Column name must match (case-insensitive)
        if self.column.lower() != other.column.lower():
            return False

        # Operator must match exactly
        if self.operator != other.operator:
            return False

        # For NULL checks, no value comparison needed
        if self.operator in (Operator.IS_NULL, Operator.IS_NOT_NULL):
            return True

        # For other operators, value matching is optional (parameterized queries)
        # We consider it a match if either:
        # 1. Both have no value (parameterized)
        # 2. Values are equal
        if self.value is None or other.value is None:
            return True

        return str(self.value).lower() == str(other.value).lower()

    def __repr__(self) -> str:
        if self.operator in (Operator.IS_NULL, Operator.IS_NOT_NULL):
            return f"{self.column} {self.operator.value}"
        return f"{self.column} {self.operator.value} {self.value}"


@dataclass
class MatchResult:
    """Result of WHERE clause comparison."""
    matched: List[NormalizedCondition]
    missing: List[NormalizedCondition]  # In SQL but not in code
    extra: List[NormalizedCondition]    # In code but not in SQL
    match_percentage: float

    @property
    def is_complete_match(self) -> bool:
        """True if all SQL conditions are present in code (extra conditions allowed)."""
        return len(self.missing) == 0

    @property
    def is_perfect_match(self) -> bool:
        """True if conditions match exactly (no missing or extra)."""
        return len(self.missing) == 0 and len(self.extra) == 0


class WhereClauseParser:
    """Extracts WHERE conditions from SQL queries and Ruby/Rails code."""

    def __init__(self, project_root: Optional[str] = None, model_scope_analyzer=None):
        """
        Initialize parser with optional Rails project context for scope resolution.

        Args:
            project_root: Path to Rails project root (enables scope resolution)
            model_scope_analyzer: Optional ModelScopeAnalyzer instance (lazy-loaded if needed)
        """
        self.parser = sqlglot
        self.project_root = project_root
        self._scope_analyzer = model_scope_analyzer
        self._scope_cache: Dict[str, Any] = {}  # Cache resolved scopes
        self._custom_finder_detector: Optional[CustomFinderDetector] = None  # Lazy-loaded

    def parse_sql(self, sql: str) -> List[NormalizedCondition]:
        """
        Parse WHERE conditions from SQL query.

        Uses regex-based extraction for reliability.
        TODO: Investigate sqlglot issues for future optimization.
        """
        return self._parse_sql_regex_fallback(sql)

    def _extract_from_where_node(self, where: exp.Where) -> List[NormalizedCondition]:
        """Extract conditions from sqlglot WHERE node."""
        conditions = []
        seen = set()  # Track what we've processed (using string representation)

        # Handle IS NOT NULL (exp.Not with exp.Is child)
        for not_expr in where.find_all(exp.Not):
            if isinstance(not_expr.this, exp.Is) and isinstance(not_expr.this.this, exp.Column):
                column = self._normalize_column_name(not_expr.this.this.name)
                key = f"{column}::IS_NOT_NULL"
                if key not in seen:
                    conditions.append(NormalizedCondition(
                        column=column,
                        operator=Operator.IS_NOT_NULL,
                        raw_pattern=str(not_expr)
                    ))
                    seen.add(key)
                    # Also mark that we've seen this column's IS expression
                    seen.add(f"IS::{column}")

        # Handle IS NULL (exp.Is)
        for is_expr in where.find_all(exp.Is):
            if isinstance(is_expr.this, exp.Column):
                column = self._normalize_column_name(is_expr.this.name)

                # Skip if already processed as part of IS NOT NULL
                if f"IS::{column}" in seen:
                    continue

                key = f"{column}::IS_NULL"
                if key not in seen:
                    conditions.append(NormalizedCondition(
                        column=column,
                        operator=Operator.IS_NULL,
                        raw_pattern=str(is_expr)
                    ))
                    seen.add(key)

        # Handle binary operations (=, !=, <, >, etc.)
        for binary_op in where.find_all(exp.Binary):
            if isinstance(binary_op.left, exp.Column):
                column = self._normalize_column_name(binary_op.left.name)
                operator = Operator.from_sqlglot(binary_op.key)

                # Extract value if it's a literal
                value = None
                if isinstance(binary_op.right, exp.Literal):
                    value = binary_op.right.this

                # Use string representation for deduplication
                key = f"{column}::{operator.name}::{value}"
                if key not in seen:
                    conditions.append(NormalizedCondition(
                        column=column,
                        operator=operator,
                        value=value,
                        raw_pattern=str(binary_op)
                    ))
                    seen.add(key)

        return conditions

    def _parse_sql_regex_fallback(self, sql: str) -> List[NormalizedCondition]:
        """Fallback regex-based WHERE parsing when sqlglot fails."""
        conditions = []

        # Extract WHERE clause
        where_match = re.search(r'WHERE\s+(.+?)(?:ORDER BY|LIMIT|OFFSET|GROUP BY|$)',
                               sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return conditions

        where_clause = where_match.group(1).strip()

        # Split by AND (simple approach)
        parts = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)

        for part in parts:
            part = part.strip()

            # IS NOT NULL pattern
            # Matches: column, table.column, `table`.`column`
            match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s+IS\s+NOT\s+NULL', part, re.IGNORECASE)
            if match:
                conditions.append(NormalizedCondition(
                    column=self._normalize_column_name(match.group(1)),
                    operator=Operator.IS_NOT_NULL,
                    raw_pattern=part
                ))
                continue

            # IS NULL pattern
            # Matches: column, table.column, `table`.`column`
            match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s+IS\s+NULL', part, re.IGNORECASE)
            if match:
                conditions.append(NormalizedCondition(
                    column=self._normalize_column_name(match.group(1)),
                    operator=Operator.IS_NULL,
                    raw_pattern=part
                ))
                continue

            # Binary operators (=, !=, <, >, etc.)
            # Matches: column, table.column, `table`.`column`
            match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s*(=|!=|<>|<=|>=|<|>)\s*(.+)', part)
            if match:
                column = self._normalize_column_name(match.group(1))
                op_str = match.group(2)
                value = match.group(3).strip().strip("'\"")

                op_map = {
                    "=": Operator.EQ,
                    "!=": Operator.NEQ,
                    "<>": Operator.NEQ,
                    "<": Operator.LT,
                    "<=": Operator.LTE,
                    ">": Operator.GT,
                    ">=": Operator.GTE,
                }

                conditions.append(NormalizedCondition(
                    column=column,
                    operator=op_map.get(op_str, Operator.UNKNOWN),
                    value=value,
                    raw_pattern=part
                ))

        return conditions

    def _detect_association_foreign_key(self, code: str) -> Optional[str]:
        """
        Detect association chains and infer the foreign key column.

        Examples:
            "company.members.active" → "company_id"
            "@user.posts.published" → "user_id"
            "project.tasks" → "project_id"
            "company.find_all_active" → "company_id" (custom finder method)

        Returns:
            Foreign key column name, or None if no association detected
        """
        # Strategy 1: Standard association chains (variable.association_name)
        # Pattern: variable.association_name (where association is plural)
        # Example: company.members → "members" is likely an association
        association_pattern = re.compile(r'(@?\w+)\.(\w+s)\.')
        match = association_pattern.search(code)

        if match:
            parent_name = match.group(1).lstrip('@')
            # Convert parent name to foreign key
            # "company" → "company_id"
            # "user" → "user_id"
            # "project" → "project_id"
            return f"{parent_name}_id"

        # Strategy 2: Custom finder methods (e.g., company.find_all_active)
        # These methods typically filter by parent's foreign key
        # Pattern: variable.find_all_*, variable.all_*, variable.get_all_*, etc.
        finder_pattern = re.compile(r'(@?\w+)\.(find_all_|all_|get_all_)\w+')
        finder_match = finder_pattern.search(code)

        if finder_match:
            parent_name = finder_match.group(1).lstrip('@')
            return f"{parent_name}_id"

        return None

    def _detect_scope_chains(self, code: str) -> List[Tuple[str, str]]:
        """
        Detect Rails scope chains in code.

        Returns:
            List of (model_name, scope_name) tuples
            Examples:
                "Member.active.visible" → [("Member", "active"), ("Member", "visible")]
                "company.members.active" → [("Member", "active")]
                "@user.posts.published" → [("Post", "published")]
        """
        scope_chains = []

        # ActiveRecord query methods (not scopes)
        query_methods = {
            'where', 'not', 'order', 'limit', 'offset', 'select', 'joins', 'includes',
            'group', 'having', 'distinct', 'readonly', 'lock', 'references', 'eager_load',
            'preload', 'from', 'unscope', 'only', 'except', 'extending',
            'new', 'create', 'create!', 'find', 'find_by', 'find_by!',
            'all', 'first', 'first!', 'last', 'last!', 'take', 'take!',
            'exists?', 'any?', 'many?', 'none?', 'one?',
            'count', 'sum', 'average', 'minimum', 'maximum', 'calculate',
            'pluck', 'ids', 'pick',
            'destroy', 'destroy_all', 'delete', 'delete_all', 'update', 'update_all',
            'find_each', 'find_in_batches', 'in_batches'
        }

        model_name = None

        # Strategy 1: Try to find direct model reference (capitalized name)
        # Example: Member.active.visible
        model_pattern = re.compile(r'\b([A-Z]\w+)\.')
        model_match = model_pattern.search(code)

        if model_match:
            model_name = model_match.group(1)
        else:
            # Strategy 2: Try to detect association chain
            # Example: company.members.active → "members" is the association (plural)
            # Example: @user.posts.published → "posts" is the association (plural)
            association_pattern = re.compile(r'(?:@?\w+)\.(\w+s)\.')
            association_match = association_pattern.search(code)

            if association_match:
                # Found an association (likely plural table name)
                # Example: "members" → singularize to "Member"
                association_name = association_match.group(1)
                model_name = self._singularize_model_name(association_name)

        # If no model found, cannot detect scopes
        if not model_name:
            return scope_chains

        # Step 2: Find all .method_name patterns after the model/association
        # This handles chains like: Member.where(...).active.limit(...)
        # We use a simple pattern and filter later to avoid overlapping match issues
        method_pattern = re.compile(r'\.(\w+)')
        method_matches = method_pattern.finditer(code)

        # Step 3: Filter out query methods and collect potential scopes
        for method_match in method_matches:
            method = method_match.group(1)
            if method not in query_methods:
                scope_chains.append((model_name, method))

        return scope_chains

    def _parse_custom_finder_method(self, code: str) -> Optional[tuple]:
        """
        Parse custom finder methods by auto-detecting them via method body analysis.

        Uses CustomFinderDetector to identify ANY instance method that returns an
        ActiveRecord relation, eliminating hardcoded naming patterns (find_*, get_*, all_*).

        Examples:
            "company.find_all_active" → reads Company#find_all_active → "members.active"
            "@user.fetch_published" → reads User#fetch_published → "posts.published"
            "order.load_recent_items" → reads Order#load_recent_items → "items.recent"

        Returns:
            Tuple of (method_body, variable_name, method_name) if found, or None
            This allows the caller to correctly identify which method call to expand
        """
        if not self.project_root:
            return None

        # Lazy-load CustomFinderDetector
        if self._custom_finder_detector is None:
            self._custom_finder_detector = CustomFinderDetector(
                project_root=self.project_root,
                debug=False
            )

        # Pattern: Match ANY method call on an instance variable
        # Example: company.find_all_active, user.fetch_published, order.load_recent
        # This is much more general than the old hardcoded pattern
        method_call_pattern = re.compile(r'\b(@?\w+)\.(\w+)\b')

        # Try ALL method calls in the code until we find a custom finder
        # This handles cases where code snippet has multiple method calls
        # Example: "VirtualCollection.new(page_size) do |page| company.find_all_active.offset..."
        #          Should match company.find_all_active, not VirtualCollection.new
        for match in method_call_pattern.finditer(code):
            variable_name = match.group(1).lstrip('@')
            method_name = match.group(2)

            # Skip standard ActiveRecord methods (these are not custom finders)
            if method_name in CustomFinderDetector.STANDARD_AR_METHODS:
                continue

            # Infer model name from variable (company → Company, user → User)
            model_name = variable_name.capitalize()

            # Use detector to check if this is a custom finder and get method body
            method_body = self._custom_finder_detector.get_method_body(model_name, method_name)

            if method_body:
                # Found a custom finder! Extract and return its body
                # Extract the likely return value (last non-comment line)
                lines = [line.strip() for line in method_body.split('\n')
                         if line.strip() and not line.strip().startswith('#')]

                if lines:
                    # Return tuple: (method_body, variable_name, method_name)
                    # This allows the caller to find the SPECIFIC method call to expand
                    return (lines[-1], variable_name, method_name)

        # No custom finder found in any of the method calls
        return None

    def _singularize_model_name(self, name: str) -> str:
        """
        Convert Rails table name (plural) to model class name (singular).

        Uses Rails ActiveSupport inflection rules for accurate singularization.

        Examples:
            members -> Member
            companies -> Company
            people -> Person
            analyses -> Analysis
        """
        # Singularize the table name
        singular = singularize(name)

        # Capitalize for model class name (handles snake_case too)
        # e.g., "page_views" -> "page_view" -> "PageView"
        return "".join(part.capitalize() for part in singular.split("_"))

    def _infer_condition_from_scope_name(self, scope_name: str) -> Optional[NormalizedCondition]:
        """
        Heuristically infer a WHERE condition from a scope name using naming conventions.

        Common Rails scope naming patterns:
        - for_X(value) → WHERE X = value (e.g., for_custom_domain → custom_domain)
        - by_X(value) → WHERE X = value (e.g., by_status → status)
        - with_X(value) → WHERE X = value (e.g., with_email → email)
        - X_is(value) → WHERE X = value (e.g., status_is → status)
        - having_X → WHERE X IS NOT NULL (e.g., having_email → email IS NOT NULL)
        - without_X → WHERE X IS NULL (e.g., without_email → email IS NULL)

        Args:
            scope_name: The scope method name

        Returns:
            NormalizedCondition if pattern matches, None otherwise
        """
        scope_lower = scope_name.lower()

        # Pattern 1: for_X(value) → WHERE X = value
        if scope_lower.startswith('for_'):
            column = scope_lower[4:]  # Remove 'for_' prefix
            return NormalizedCondition(
                column=column,
                operator=Operator.EQ,
                value=None,  # Parameterized
                raw_pattern=f"heuristic: {scope_name} → {column} = ?"
            )

        # Pattern 2: by_X(value) → WHERE X = value
        if scope_lower.startswith('by_'):
            column = scope_lower[3:]  # Remove 'by_' prefix
            return NormalizedCondition(
                column=column,
                operator=Operator.EQ,
                value=None,
                raw_pattern=f"heuristic: {scope_name} → {column} = ?"
            )

        # Pattern 3: with_X(value) → WHERE X = value (or IS NOT NULL if no args)
        if scope_lower.startswith('with_'):
            column = scope_lower[5:]  # Remove 'with_' prefix
            # Typically with_ means "with value" so assume = ?
            return NormalizedCondition(
                column=column,
                operator=Operator.EQ,
                value=None,
                raw_pattern=f"heuristic: {scope_name} → {column} = ?"
            )

        # Pattern 4: having_X → WHERE X IS NOT NULL
        if scope_lower.startswith('having_'):
            column = scope_lower[7:]  # Remove 'having_' prefix
            return NormalizedCondition(
                column=column,
                operator=Operator.IS_NOT_NULL,
                raw_pattern=f"heuristic: {scope_name} → {column} IS NOT NULL"
            )

        # Pattern 5: without_X → WHERE X IS NULL
        if scope_lower.startswith('without_'):
            column = scope_lower[8:]  # Remove 'without_' prefix
            return NormalizedCondition(
                column=column,
                operator=Operator.IS_NULL,
                raw_pattern=f"heuristic: {scope_name} → {column} IS NULL"
            )

        # Pattern 6: X_is(value) → WHERE X = value
        if scope_lower.endswith('_is'):
            column = scope_lower[:-3]  # Remove '_is' suffix
            return NormalizedCondition(
                column=column,
                operator=Operator.EQ,
                value=None,
                raw_pattern=f"heuristic: {scope_name} → {column} = ?"
            )

        return None

    def _resolve_scope_conditions(self, model_name: str, scope_name: str) -> List[NormalizedCondition]:
        """
        Resolve a Rails scope to its WHERE conditions.

        Strategy:
        1. Try to parse the scope definition from the model file
        2. If parsing fails or scope not found, use heuristic matching from scope name

        Args:
            model_name: Rails model name (e.g., "Member" or "members")
            scope_name: Scope name (e.g., "active", "for_custom_domain")

        Returns:
            List of NormalizedCondition objects from the scope definition
        """
        if not self.project_root:
            # No project context, try heuristic only
            heuristic_cond = self._infer_condition_from_scope_name(scope_name)
            return [heuristic_cond] if heuristic_cond else []

        # Normalize model name: handle both singular (Member) and plural (members) table names
        # Convert to singular form for model file lookup
        model_name_singular = self._singularize_model_name(model_name)

        # Check cache first
        cache_key = f"{model_name_singular}.{scope_name}"
        if cache_key in self._scope_cache:
            return self._scope_cache[cache_key]

        # Lazy-load ModelScopeAnalyzer if needed
        if self._scope_analyzer is None:
            try:
                from .model_scope_analyzer import ModelScopeAnalyzer
                self._scope_analyzer = ModelScopeAnalyzer(debug=False)
            except ImportError:
                # Fallback to heuristic
                heuristic_cond = self._infer_condition_from_scope_name(scope_name)
                result = [heuristic_cond] if heuristic_cond else []
                self._scope_cache[cache_key] = result
                return result

        # Find the model file (use lowercase singular name)
        model_file = Path(self.project_root) / "app" / "models" / f"{model_name_singular.lower()}.rb"
        if not model_file.exists():
            # Model file not found, try heuristic
            heuristic_cond = self._infer_condition_from_scope_name(scope_name)
            result = [heuristic_cond] if heuristic_cond else []
            self._scope_cache[cache_key] = result
            return result

        # Analyze the model to extract scope definitions
        scopes = self._scope_analyzer.analyze_model(str(model_file))

        if scope_name not in scopes:
            # Scope not found in model, try heuristic
            heuristic_cond = self._infer_condition_from_scope_name(scope_name)
            result = [heuristic_cond] if heuristic_cond else []
            self._scope_cache[cache_key] = result
            return result

        # Convert scope's NormalizedClause objects to NormalizedCondition objects
        scope_def = scopes[scope_name]

        # If scope has no WHERE clauses (e.g., complex scope that couldn't be parsed),
        # fall back to heuristic matching
        if not scope_def.where_clauses:
            heuristic_cond = self._infer_condition_from_scope_name(scope_name)
            result = [heuristic_cond] if heuristic_cond else []
            self._scope_cache[cache_key] = result
            return result

        conditions = []
        for clause in scope_def.where_clauses:
            # Map operator strings to Operator enum
            operator_map = {
                "IS_NULL": Operator.IS_NULL,
                "IS_NOT_NULL": Operator.IS_NOT_NULL,
                "=": Operator.EQ,
                "!=": Operator.NEQ,
                "<": Operator.LT,
                "<=": Operator.LTE,
                ">": Operator.GT,
                ">=": Operator.GTE,
            }

            operator = operator_map.get(clause.operator, Operator.UNKNOWN)

            conditions.append(NormalizedCondition(
                column=clause.column,
                operator=operator,
                value=getattr(clause, 'value', None),
                raw_pattern=f"scope :{scope_name}"
            ))

        self._scope_cache[cache_key] = conditions
        return conditions

    def parse_ruby_code(self, code: str) -> List[NormalizedCondition]:
        """
        Parse WHERE conditions from Ruby/Rails code snippet.

        Extracts conditions from patterns like:
        - .where("column IS NOT NULL")
        - .where(column: value)
        - .where("column = ?", value)
        - Rails scopes (e.g., Member.active)
        - Association chains (e.g., company.members → implies company_id filter)
        - Custom finder methods (parses method body to extract actual code)
        """
        conditions = []

        # NEW: Try to parse custom finder method bodies
        # Example: company.find_all_active → reads method body → "members.active"
        # Then recursively parse the method body (but only once to avoid infinite recursion)
        finder_info = self._parse_custom_finder_method(code)
        if finder_info:
            # Unpack the tuple: (method_body, variable_name, method_name)
            method_body, found_var, found_method = finder_info

            # Found a custom method - parse its body recursively
            # Preserve the parent context for foreign key detection
            # Example: company.find_all_active.offset(...).limit(...).order(...)
            # → method returns "members.active"
            # We want to parse "company.members.active.offset(...).limit(...).order(...)"

            # Build a specific pattern to find THIS method call (not just the first one)
            # This fixes the bug where VirtualCollection.new was matched instead of company.find_all_active
            # Escape special regex characters in variable and method names
            escaped_var = re.escape(found_var)
            escaped_method = re.escape(found_method)

            # Match the SPECIFIC method call we detected, and capture the rest of the chain
            # Stop at Ruby statement terminators: comments (#), semicolons (;), blocks ({, do)
            specific_method_pattern = re.compile(
                rf'\b(@?{escaped_var})\.({escaped_method})'  # The specific variable.method we found
                r'([^#;{]*?)'  # Rest of chain (non-greedy), stop at terminators
                r'(?=\s*(?:#|;|{|\bdo\b|\bif\b|\bunless\b|\bend\b|$))'  # Lookahead for boundaries
            )
            finder_match = specific_method_pattern.search(code)

            if finder_match:
                parent_var = finder_match.group(1).lstrip('@')
                rest_of_chain = finder_match.group(3)  # Everything after the method name

                # Prepend parent and append rest: "company" + "members.active" + ".offset(...).limit(...)"
                expanded_code = f"{parent_var}.{method_body}{rest_of_chain}"

                # DEBUG
                # print(f"DEBUG: Expanding custom finder method")
                # print(f"  Parent: {parent_var}")
                # print(f"  Method: {found_method}")
                # print(f"  Method body: {method_body}")
                # print(f"  Rest of chain: {rest_of_chain[:100]}")
                # print(f"  Expanded: {expanded_code[:150]}")

                # Recursively parse the expanded code (will NOT match finder pattern again)
                result = self.parse_ruby_code(expanded_code)
                # print(f"  Recursive call returned {len(result)} conditions")
                return result

        # Detect association chains and add implicit foreign key conditions
        # Example: company.members.active → adds implicit "company_id = ?" condition
        association_fk = self._detect_association_foreign_key(code)
        if association_fk:
            conditions.append(NormalizedCondition(
                column=association_fk,
                operator=Operator.EQ,
                value=None,  # Runtime value
                raw_pattern=f"association foreign key: {association_fk}"
            ))

        # Detect and resolve scope chains
        scope_chains = self._detect_scope_chains(code)
        for model_name, scope_name in scope_chains:
            scope_conditions = self._resolve_scope_conditions(model_name, scope_name)
            conditions.extend(scope_conditions)

        # Find all .where() calls - simpler regex
        where_patterns = re.finditer(
            r'\.where\s*\(([^)]+)\)',
            code,
            re.IGNORECASE | re.DOTALL
        )

        for match in where_patterns:
            where_content = match.group(1).strip()

            # Check if it's a string literal (starts with quote)
            is_string_literal = where_content.startswith('"') or where_content.startswith("'")

            # Parse string-based WHERE clauses (SQL-like)
            if is_string_literal:
                # Remove quotes
                where_content = where_content.strip('"\'')

                # SQL-like string: "column IS NOT NULL AND other_column = ?"
                # Split by AND
                parts = re.split(r'\s+AND\s+', where_content, flags=re.IGNORECASE)

                for part in parts:
                    part = part.strip()
                    if not part:
                        continue

                    # IS NOT NULL
                    # Matches: column, table.column, `table`.`column`
                    col_match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s+IS\s+NOT\s+NULL', part, re.IGNORECASE)
                    if col_match:
                        conditions.append(NormalizedCondition(
                            column=self._normalize_column_name(col_match.group(1)),
                            operator=Operator.IS_NOT_NULL,
                            raw_pattern=part
                        ))
                        continue

                    # IS NULL
                    # Matches: column, table.column, `table`.`column`
                    col_match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s+IS\s+NULL', part, re.IGNORECASE)
                    if col_match:
                        conditions.append(NormalizedCondition(
                            column=self._normalize_column_name(col_match.group(1)),
                            operator=Operator.IS_NULL,
                            raw_pattern=part
                        ))
                        continue

                    # Other operators
                    # Matches: column, table.column, `table`.`column`
                    col_match = re.search(r'((?:`?\w+`?\.)?`?\w+`?)\s*(=|!=|<>|<=|>=|<|>)', part)
                    if col_match:
                        column = self._normalize_column_name(col_match.group(1))
                        operator = Operator.from_ruby_pattern(part)
                        conditions.append(NormalizedCondition(
                            column=column,
                            operator=operator,
                            raw_pattern=part
                        ))

            # Parse hash-based WHERE clauses
            # .where(column: value, other: value)
            else:
                hash_pairs = re.finditer(r'(\w+)\s*:\s*([^,)]+)', where_content)
                for pair in hash_pairs:
                    column = self._normalize_column_name(pair.group(1))
                    value = pair.group(2).strip()

                    # Check for nil
                    if value.lower() == 'nil':
                        conditions.append(NormalizedCondition(
                            column=column,
                            operator=Operator.IS_NULL,
                            raw_pattern=f"{column}: nil"
                        ))
                    else:
                        # Check if value is a literal (string/number) or expression
                        # Literals: '123', '"text"', ':symbol'
                        # Expressions: variable, method.call, etc.
                        is_literal = (
                            value.isdigit() or  # Pure number
                            (value.startswith(("'", '"')) and value.endswith(("'", '"'))) or  # String
                            value.startswith(":")  # Symbol
                        )

                        conditions.append(NormalizedCondition(
                            column=column,
                            operator=Operator.EQ,
                            value=value if is_literal else None,  # None for expressions = parameterized
                            raw_pattern=f"{column}: {value}"
                        ))

        return conditions

    def _normalize_column_name(self, column: str) -> str:
        """Normalize column name for comparison (lowercase, remove table prefix)."""
        # Remove table prefix (e.g., "members.id" -> "id")
        if "." in column:
            column = column.split(".")[-1]

        # Remove backticks/quotes
        column = column.strip('"`\'')

        return column.lower()


class WhereClauseMatcher:
    """Semantic matcher for comparing WHERE clauses between SQL and Ruby code."""

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize matcher with optional Rails project context.

        Args:
            project_root: Path to Rails project root (enables scope resolution)
        """
        self.parser = WhereClauseParser(project_root=project_root)

    def match(
        self,
        sql_conditions: List[NormalizedCondition],
        code_conditions: List[NormalizedCondition]
    ) -> MatchResult:
        """
        Compare SQL WHERE conditions with code WHERE conditions.

        Returns detailed match result showing matched, missing, and extra conditions.
        """
        matched = []
        missing = []
        extra = list(code_conditions)  # Start with all code conditions as "extra"

        for sql_cond in sql_conditions:
            found = False
            for i, code_cond in enumerate(extra):
                if sql_cond.matches(code_cond):
                    matched.append(sql_cond)
                    extra.pop(i)  # Remove from extra since it's matched
                    found = True
                    break

            if not found:
                missing.append(sql_cond)

        # Calculate match percentage
        if len(sql_conditions) == 0:
            match_percentage = 1.0
        else:
            match_percentage = len(matched) / len(sql_conditions)

        return MatchResult(
            matched=matched,
            missing=missing,
            extra=extra,
            match_percentage=match_percentage
        )

    def match_sql_to_code(self, sql: str, code: str) -> MatchResult:
        """
        Parse and match WHERE conditions from SQL query to Ruby code.

        Convenience method that handles parsing internally.
        """
        sql_conditions = self.parser.parse_sql(sql)
        code_conditions = self.parser.parse_ruby_code(code)

        return self.match(sql_conditions, code_conditions)
