"""
SQL-to-Scope Matcher - Semantic matching of SQL queries to Rails scopes.

This module provides semantic matching between SQL WHERE clauses
and Rails scope definitions extracted from model files.
"""
from __future__ import annotations

import re
from typing import Dict, Set, List

from .scope_definitions import (
    NormalizedClause,
    ScopeDefinition,
    ScopeMatch
)


class SQLToScopeMatcher:
    """
    Matches SQL WHERE clauses to Rails scope definitions semantically.

    Workflow:
    1. Normalize SQL WHERE clauses to NormalizedClause format
    2. For each scope, calculate match score
    3. Return ranked list of matching scopes

    Example:
        SQL: WHERE login_handle IS NOT NULL AND owner_id IS NULL
        Scopes:
          - :all_canonical → perfect match (1.0)
          - :not_disabled → partial match (0.8)
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def find_matching_scopes(
        self,
        sql_analysis: any,
        scopes: Dict[str, ScopeDefinition]
    ) -> List[ScopeMatch]:
        """
        Find all scopes that match the SQL WHERE clauses.

        Args:
            sql_analysis: SQL analysis object with where_conditions attribute
            scopes: Dict of scope definitions from model

        Returns:
            Sorted list of ScopeMatch objects (best match first)
        """
        # Normalize SQL WHERE clauses
        sql_clauses = self._normalize_sql_where(sql_analysis)

        if not sql_clauses:
            if self.debug:
                print("No WHERE clauses in SQL")
            return []

        # Match against each scope
        matches = []
        for scope_name, scope_def in scopes.items():
            match = self._match_scope(scope_name, scope_def, sql_clauses)
            if match.confidence > 0.0:
                matches.append(match)

        # Sort by confidence (highest first)
        matches.sort(key=lambda m: m.confidence, reverse=True)

        if self.debug:
            print(f"Found {len(matches)} matching scopes:")
            for match in matches[:5]:  # Show top 5
                print(f"  - {match.name}: {match.confidence:.2f} confidence")

        return matches

    def _normalize_sql_where(self, sql_analysis: any) -> Set[NormalizedClause]:
        """
        Convert SQL WHERE clauses to normalized form.

        Extracts WHERE conditions from sql_analysis and converts to NormalizedClause.
        """
        clauses: Set[NormalizedClause] = set()

        # Get WHERE conditions from analysis
        where_conditions = getattr(sql_analysis, 'where_conditions', [])

        for condition in where_conditions:
            # Each condition has: column, operator, value
            column = getattr(condition.column, 'name', str(condition.column))
            operator = getattr(condition, 'operator', '=')
            value = getattr(condition, 'value', None)

            # Normalize operator
            normalized_op = self._normalize_operator(operator, value)

            # Create normalized clause
            if normalized_op in ('IS_NULL', 'IS_NOT_NULL'):
                clauses.add(NormalizedClause(column=column, operator=normalized_op))
            else:
                # For values, use "?" to indicate parameterized
                clause_value = '?' if value is None else str(value)
                clauses.add(NormalizedClause(
                    column=column,
                    operator=normalized_op,
                    value=clause_value
                ))

        # Also try parsing raw SQL if available
        raw_sql = getattr(sql_analysis, 'raw_sql', '')
        if raw_sql:
            clauses.update(self._parse_raw_sql_where(raw_sql))

        return clauses

    def _normalize_operator(self, operator: str, value: any) -> str:
        """
        Normalize SQL operators to canonical form.

        Examples:
        - "=" with NULL → "IS_NULL"
        - "!=" with NULL → "IS_NOT_NULL"
        - "IS" with NULL → "IS_NULL"
        - "=" with value → "="
        """
        op_lower = str(operator).lower().strip()

        # Handle NULL comparisons
        if value is None or str(value).upper() == 'NULL':
            if op_lower in ('=', 'is'):
                return 'IS_NULL'
            elif op_lower in ('!=', '<>', 'is not'):
                return 'IS_NOT_NULL'

        # Standard operators
        operator_map = {
            '=': '=',
            '==': '=',
            '!=': '!=',
            '<>': '!=',
            '>': '>',
            '<': '<',
            '>=': '>=',
            '<=': '<=',
            'like': 'LIKE',
            'ilike': 'ILIKE',
        }

        return operator_map.get(op_lower, op_lower.upper())

    def _parse_raw_sql_where(self, raw_sql: str) -> Set[NormalizedClause]:
        """
        Parse WHERE clauses from raw SQL string.

        This handles cases where WHERE conditions aren't fully parsed
        by the SQL analyzer.
        """
        clauses: Set[NormalizedClause] = set()

        # Extract WHERE clause
        where_match = re.search(r'\bWHERE\s+(.+?)(?:\s+ORDER\s+BY|\s+LIMIT|\s+OFFSET|$)',
                               raw_sql, re.IGNORECASE | re.DOTALL)
        if not where_match:
            return clauses

        where_clause = where_match.group(1)

        # Split on AND/OR
        conditions = re.split(r'\s+AND\s+|\s+OR\s+', where_clause, flags=re.IGNORECASE)

        for condition in conditions:
            condition = condition.strip()

            # IS NULL
            match = re.match(r'`?(\w+\.)?(\w+)`?\s+IS\s+NULL', condition, re.IGNORECASE)
            if match:
                column = match.group(2)
                clauses.add(NormalizedClause(column=column, operator='IS_NULL'))
                continue

            # IS NOT NULL
            match = re.match(r'`?(\w+\.)?(\w+)`?\s+IS\s+NOT\s+NULL', condition, re.IGNORECASE)
            if match:
                column = match.group(2)
                clauses.add(NormalizedClause(column=column, operator='IS_NOT_NULL'))
                continue

            # column = value (with optional table prefix)
            match = re.match(r'`?(\w+\.)?(\w+)`?\s*=\s*(.+)', condition)
            if match:
                column = match.group(2)
                value = match.group(3).strip().strip("'\"")
                # Use ? for parameterized values
                if re.match(r'^\d+$', value):
                    value = '?'
                clauses.add(NormalizedClause(column=column, operator='=', value=value))
                continue

        return clauses

    def _match_scope(
        self,
        scope_name: str,
        scope_def: ScopeDefinition,
        sql_clauses: Set[NormalizedClause]
    ) -> ScopeMatch:
        """
        Calculate how well a scope matches the SQL clauses.

        Returns ScopeMatch with confidence score and clause breakdown.
        """
        # Find matching clauses
        matched = set()
        for sql_clause in sql_clauses:
            for scope_clause in scope_def.where_clauses:
                if scope_clause.matches(sql_clause):
                    matched.add(sql_clause)
                    break

        # Calculate missing and extra clauses
        missing = sql_clauses - matched
        extra = scope_def.where_clauses - set(
            sc for sc in scope_def.where_clauses
            if any(sc.matches(sql) for sql in sql_clauses)
        )

        # Calculate confidence score
        confidence = scope_def.get_match_score(sql_clauses)

        return ScopeMatch(
            name=scope_name,
            confidence=confidence,
            matched_clauses=matched,
            missing_clauses=missing,
            extra_clauses=extra,
            scope_definition=scope_def
        )
