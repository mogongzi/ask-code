"""
Model Scope Analyzer - Extract and resolve scope definitions from Rails models.

This module provides semantic analysis of Rails model files to extract:
1. All scope definitions
2. SQL condition constants (ACTIVE_COND, etc.)
3. Resolved scope chains (when scopes call other scopes)
4. Normalized WHERE clauses for semantic matching
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, Set, List, Optional, Tuple

from .scope_definitions import (
    NormalizedClause,
    ScopeDefinition,
    RawScope
)


class ModelScopeAnalyzer:
    """
    Analyzes Rails model files to extract scope definitions.

    Main workflow:
    1. Read model file
    2. Extract all scopes (grep for 'scope :name')
    3. Extract constants (ACTIVE_COND, etc.)
    4. Parse each scope's WHERE clauses
    5. Resolve scope chains (active → not_disabled → all_canonical)
    6. Return normalized ScopeDefinition objects
    """

    def __init__(self, debug: bool = False):
        self.debug = debug

    def analyze_model(self, model_file: str) -> Dict[str, ScopeDefinition]:
        """
        Extract all scopes from a Rails model file.

        Args:
            model_file: Path to the model file (e.g., app/models/member.rb)

        Returns:
            Dict mapping scope name to ScopeDefinition with resolved WHERE clauses
        """
        if not Path(model_file).exists():
            if self.debug:
                print(f"Model file not found: {model_file}")
            return {}

        # Step 1: Read file content
        with open(model_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        # Step 2: Extract raw scopes
        raw_scopes = self._extract_scopes(content)

        # Step 3: Extract constants
        constants = self._extract_constants(content)

        # Step 4: Resolve scope chains and normalize
        resolved_scopes = self._resolve_scope_chains(raw_scopes, constants)

        if self.debug:
            print(f"Extracted {len(resolved_scopes)} scopes from {model_file}")
            for name, scope in resolved_scopes.items():
                print(f"  - {name}: {len(scope.where_clauses)} WHERE clauses")

        return resolved_scopes

    def _extract_scopes(self, content: str) -> Dict[str, RawScope]:
        """
        Extract all scope definitions from model content.

        Patterns matched:
        - scope :name, -> { where(...) }
        - scope :name, lambda { |param| where(...) }
        - scope(:name, -> { where(...) })
        """
        scopes = {}
        lines = content.split('\n')

        # Find all lines that start scope definitions
        scope_pattern = re.compile(r'^\s*scope\s+:(\w+)')

        i = 0
        while i < len(lines):
            line = lines[i]
            match = scope_pattern.match(line)

            if match:
                scope_name = match.group(1)
                scope_def, end_line = self._extract_scope_body(lines, i)

                scopes[scope_name] = RawScope(
                    name=scope_name,
                    definition=scope_def,
                    line_number=i + 1,
                    calls_scope=self._detect_scope_call(scope_def)
                )

                i = end_line
            i += 1

        return scopes

    def _extract_scope_body(self, lines: List[str], start_line: int) -> Tuple[str, int]:
        """
        Extract the complete scope definition, handling multi-line scopes.

        Returns:
            (scope_definition_string, end_line_index)
        """
        definition = lines[start_line]
        i = start_line

        # Count braces/do-end to find scope end
        open_braces = definition.count('{') - definition.count('}')
        has_do = 'do' in definition
        has_end = 'end' in definition

        # Single-line scope
        if open_braces == 0 and (not has_do or has_end):
            return definition, start_line

        # Multi-line scope with braces
        if open_braces > 0:
            i += 1
            while i < len(lines) and open_braces > 0:
                definition += '\n' + lines[i]
                open_braces += lines[i].count('{') - lines[i].count('}')
                i += 1
            return definition, i - 1

        # Multi-line scope with do-end
        if has_do and not has_end:
            i += 1
            while i < len(lines) and 'end' not in lines[i]:
                definition += '\n' + lines[i]
                i += 1
            if i < len(lines):
                definition += '\n' + lines[i]
            return definition, i

        return definition, start_line

    def _detect_scope_call(self, scope_def: str) -> Optional[str]:
        """
        Detect if a scope calls another scope.

        Example:
            scope :active, -> { not_disabled.where(...) }
            Returns: "not_disabled"
        """
        # Pattern: scope_name.where or scope_name.method
        pattern = re.compile(r'[\{\s](\w+)\.(where|not|limit|order|offset)')
        match = pattern.search(scope_def)

        if match:
            called_scope = match.group(1)
            # Filter out common ActiveRecord methods
            if called_scope not in ['where', 'not', 'limit', 'order', 'offset', 'select', 'joins']:
                return called_scope

        return None

    def _extract_constants(self, content: str) -> Dict[str, str]:
        """
        Extract SQL condition constants from model.

        Patterns matched:
        - ACTIVE_COND = "disabler_id IS NULL AND ..."
        - CANONICAL_COND = "login_handle IS NOT NULL" + ...
        """
        constants = {}

        # Pattern: CONSTANT_NAME = "SQL string"
        pattern = re.compile(r'([A-Z_]+COND)\s*=\s*["\']([^"\']+)["\']')
        matches = pattern.findall(content)

        for const_name, sql_value in matches:
            constants[const_name] = sql_value

        # Handle string concatenation: COND1 + COND2
        concat_pattern = re.compile(r'([A-Z_]+COND)\s*=\s*["\']([^"\']+)["\']\s*\+\s*([A-Z_]+COND)')
        concat_matches = concat_pattern.findall(content)

        for const_name, sql_part, other_const in concat_matches:
            if other_const in constants:
                constants[const_name] = sql_part + ' AND ' + constants[other_const]

        return constants

    def _resolve_scope_chains(
        self,
        raw_scopes: Dict[str, RawScope],
        constants: Dict[str, str]
    ) -> Dict[str, ScopeDefinition]:
        """
        Resolve scope chains and normalize WHERE clauses.

        Example:
            scope :all_canonical, -> { where.not(login_handle: nil).where(owner_id: nil) }
            scope :not_disabled, -> { all_canonical.where(disabler_id: nil) }
            scope :active, -> { not_disabled.where.not(first_login_at: nil) }

        Resolves to:
            :active has WHERE clauses from :not_disabled + first_login_at
            :not_disabled has WHERE clauses from :all_canonical + disabler_id
            :all_canonical has WHERE clauses from its definition
        """
        resolved = {}

        # Resolve each scope (with memoization for already-resolved scopes)
        for scope_name, raw_scope in raw_scopes.items():
            if scope_name not in resolved:
                resolved[scope_name] = self._resolve_single_scope(
                    scope_name,
                    raw_scopes,
                    constants,
                    resolved
                )

        return resolved

    def _resolve_single_scope(
        self,
        scope_name: str,
        raw_scopes: Dict[str, RawScope],
        constants: Dict[str, str],
        resolved_cache: Dict[str, ScopeDefinition]
    ) -> ScopeDefinition:
        """
        Resolve a single scope, recursively resolving any scopes it calls.
        """
        if scope_name in resolved_cache:
            return resolved_cache[scope_name]

        raw_scope = raw_scopes[scope_name]
        all_clauses: Set[NormalizedClause] = set()
        composed_from = []

        # If this scope calls another scope, resolve that first
        if raw_scope.calls_scope and raw_scope.calls_scope in raw_scopes:
            called_scope_def = self._resolve_single_scope(
                raw_scope.calls_scope,
                raw_scopes,
                constants,
                resolved_cache
            )
            all_clauses.update(called_scope_def.where_clauses)
            composed_from.append(raw_scope.calls_scope)

        # Extract WHERE clauses from this scope's definition
        scope_clauses = self._parse_where_clauses(raw_scope.definition, constants)
        all_clauses.update(scope_clauses)

        scope_def = ScopeDefinition(
            name=scope_name,
            where_clauses=all_clauses,
            composed_from=composed_from,
            source_line=raw_scope.line_number,
            raw_definition=raw_scope.definition
        )

        resolved_cache[scope_name] = scope_def
        return scope_def

    def _parse_where_clauses(self, scope_def: str, constants: Dict[str, str]) -> Set[NormalizedClause]:
        """
        Parse WHERE clauses from a scope definition.

        Handles:
        - .where(column: value)
        - .where.not(column: nil)
        - .where("SQL string")
        - .where(CONSTANT)
        """
        clauses: Set[NormalizedClause] = set()

        # Pattern 1: .where(column: nil) or .where(:column => nil) → IS NULL
        # Supports both modern (column:) and old (:column =>) syntax
        nil_pattern = re.compile(r'\.where\((?::)?(\w+)(?::\s*|(?:\s*=>\s*))nil\)')
        for match in nil_pattern.finditer(scope_def):
            clauses.add(NormalizedClause(column=match.group(1), operator="IS_NULL"))

        # Pattern 2: where.not(column: nil) or .where.not(:column => nil) → IS NOT NULL
        # Matches both: where.not(...) and .where.not(...)
        # Supports both modern (column:) and old (:column =>) syntax
        not_nil_pattern = re.compile(r'(?:where)?\.not\((?::)?(\w+)(?::\s*|(?:\s*=>\s*))nil\)')
        for match in not_nil_pattern.finditer(scope_def):
            clauses.add(NormalizedClause(column=match.group(1), operator="IS_NOT_NULL"))

        # Pattern 3: .where("SQL string")
        sql_pattern = re.compile(r'\.where\(["\']([^"\']+)["\']\)')
        for match in sql_pattern.finditer(scope_def):
            sql_string = match.group(1)
            clauses.update(self._parse_sql_string(sql_string))

        # Pattern 4: .where(CONSTANT) - substitute and parse
        for const_name, const_value in constants.items():
            if const_name in scope_def:
                clauses.update(self._parse_sql_string(const_value))

        return clauses

    def _parse_sql_string(self, sql: str) -> Set[NormalizedClause]:
        """
        Parse SQL WHERE string into normalized clauses.

        Examples:
        - "disabler_id IS NULL" → NormalizedClause(column="disabler_id", operator="IS_NULL")
        - "login_handle IS NOT NULL" → NormalizedClause(column="login_handle", operator="IS_NOT_NULL")
        - "company_id = 123" → NormalizedClause(column="company_id", operator="=", value="123")
        """
        clauses: Set[NormalizedClause] = set()

        # Split on AND/OR
        conditions = re.split(r'\s+AND\s+|\s+OR\s+', sql, flags=re.IGNORECASE)

        for condition in conditions:
            condition = condition.strip()

            # IS NULL
            match = re.match(r'`?(\w+)`?\s+IS\s+NULL', condition, re.IGNORECASE)
            if match:
                clauses.add(NormalizedClause(column=match.group(1), operator="IS_NULL"))
                continue

            # IS NOT NULL
            match = re.match(r'`?(\w+)`?\s+IS\s+NOT\s+NULL', condition, re.IGNORECASE)
            if match:
                clauses.add(NormalizedClause(column=match.group(1), operator="IS_NOT_NULL"))
                continue

            # column = value
            match = re.match(r'`?(\w+)`?\s*=\s*["\']?([^"\']+)["\']?', condition)
            if match:
                clauses.add(NormalizedClause(
                    column=match.group(1),
                    operator="=",
                    value=match.group(2)
                ))
                continue

        return clauses
