"""
Data structures for semantic scope analysis.

This module defines the core data types used for:
1. Normalizing SQL and Rails WHERE clauses
2. Representing scope definitions from Rails models
3. Matching SQL queries to Rails scopes semantically
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Set, List, Optional


@dataclass(frozen=True)
class NormalizedClause:
    """
    Normalized WHERE clause for semantic comparison.

    Represents a single WHERE condition in canonical form, allowing
    comparison between SQL and Rails representations.

    Examples:
        SQL: "disabler_id IS NULL"
        → NormalizedClause(column="disabler_id", operator="IS_NULL")

        Rails: .where(disabler_id: nil)
        → NormalizedClause(column="disabler_id", operator="IS_NULL")

        SQL: "company_id = 32546"
        → NormalizedClause(column="company_id", operator="=", value="32546")

        Rails: .where.not(login_handle: nil)
        → NormalizedClause(column="login_handle", operator="IS_NOT_NULL")
    """
    column: str
    operator: str  # "IS_NULL", "IS_NOT_NULL", "=", "!=", ">", "<", "LIKE", etc.
    value: Optional[str] = None  # None for IS_NULL/IS_NOT_NULL, value for comparisons

    def __str__(self) -> str:
        if self.value is None:
            return f"{self.column} {self.operator}"
        return f"{self.column} {self.operator} {self.value}"

    def matches(self, other: NormalizedClause) -> bool:
        """
        Check if this clause semantically matches another.

        Handles:
        - Exact matches
        - Parameterized values (? in SQL)
        - Different value representations
        """
        if self.column != other.column:
            return False

        if self.operator != other.operator:
            return False

        # For NULL checks, value doesn't matter
        if self.operator in ("IS_NULL", "IS_NOT_NULL"):
            return True

        # For parameterized queries, ignore specific value
        if self.value == "?" or other.value == "?":
            return True

        # Otherwise, values must match
        return self.value == other.value


@dataclass
class ScopeDefinition:
    """
    A Rails scope with resolved WHERE conditions.

    Represents a scope from a Rails model file, with all WHERE clauses
    resolved (including composed scopes).

    Example:
        scope :active, -> { not_disabled.where.not(first_login_at: nil) }

        → ScopeDefinition(
            name="active",
            where_clauses={
                NormalizedClause(column="disabler_id", operator="IS_NULL"),
                NormalizedClause(column="login_handle", operator="IS_NOT_NULL"),
                NormalizedClause(column="owner_id", operator="IS_NULL"),
                NormalizedClause(column="first_login_at", operator="IS_NOT_NULL"),
            },
            composed_from=["not_disabled"],
            source_line=47,
            raw_definition="scope :active, -> { not_disabled.where.not(first_login_at: nil) }"
        )
    """
    name: str
    where_clauses: Set[NormalizedClause]
    composed_from: List[str] = field(default_factory=list)
    source_line: int = 0
    raw_definition: str = ""

    def matches_all_clauses(self, sql_clauses: Set[NormalizedClause]) -> bool:
        """
        Check if this scope contains ALL SQL WHERE clauses.

        Returns True if every SQL clause is present in this scope.
        """
        for sql_clause in sql_clauses:
            if not any(scope_clause.matches(sql_clause) for scope_clause in self.where_clauses):
                return False
        return True

    def get_match_score(self, sql_clauses: Set[NormalizedClause]) -> float:
        """
        Calculate how well this scope matches the SQL clauses.

        Returns:
            1.0 = Perfect match (all SQL clauses in scope, no extras)
            0.8-0.99 = Scope has all SQL clauses plus extras
            0.5-0.79 = Partial match (some SQL clauses present)
            0.0 = No match
        """
        if not sql_clauses:
            return 0.0

        # Count matching clauses
        matched = sum(
            1 for sql_clause in sql_clauses
            if any(scope_clause.matches(sql_clause) for scope_clause in self.where_clauses)
        )

        # No matches
        if matched == 0:
            return 0.0

        # Calculate base score
        base_score = matched / len(sql_clauses)

        # Perfect match: all SQL clauses present, no extra scope clauses
        if matched == len(sql_clauses) and len(self.where_clauses) == len(sql_clauses):
            return 1.0

        # All SQL clauses present, but scope has extras
        if matched == len(sql_clauses):
            return min(0.99, 0.8 + (base_score * 0.19))

        # Partial match
        return base_score * 0.7


@dataclass
class ScopeMatch:
    """
    Result of matching SQL WHERE clauses to a Rails scope.

    Contains all information about how well a scope matches the SQL,
    including which clauses matched, which are missing, and which are extra.

    Example:
        SQL: WHERE login_handle IS NOT NULL AND owner_id IS NULL
        Scope :all_canonical has those exact clauses

        → ScopeMatch(
            name="all_canonical",
            confidence=1.0,
            matched_clauses={...},
            missing_clauses=set(),
            extra_clauses=set()
        )
    """
    name: str
    confidence: float
    matched_clauses: Set[NormalizedClause]
    missing_clauses: Set[NormalizedClause]  # In SQL but not in scope
    extra_clauses: Set[NormalizedClause]    # In scope but not in SQL
    scope_definition: Optional[ScopeDefinition] = None

    def is_perfect_match(self) -> bool:
        """Returns True if all SQL clauses match and no extras."""
        return not self.missing_clauses and not self.extra_clauses

    def is_complete_match(self) -> bool:
        """Returns True if all SQL clauses are present (extras allowed)."""
        return not self.missing_clauses


@dataclass
class RawScope:
    """
    Raw scope definition before resolution.

    Represents a scope as parsed from the source file, before
    resolving scope chains or normalizing WHERE clauses.
    """
    name: str
    definition: str
    line_number: int
    calls_scope: Optional[str] = None  # e.g., "not_disabled" in "not_disabled.where(...)"
