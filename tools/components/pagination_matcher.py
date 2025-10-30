"""
Pagination Matcher - Semantic validation of LIMIT/OFFSET values.

Validates that SQL pagination parameters are compatible with Ruby/Rails code:
- LIMIT values should match
- OFFSET values should be achievable (multiples of page size)
- LIMIT/OFFSET relationship should be consistent

Example incompatibilities:
- SQL: LIMIT 500, Code: limit(1000) → Mismatch
- SQL: OFFSET 500, Code: offset((page-1)*1000) → Impossible (500 not multiple of 1000)
"""
from __future__ import annotations

import re
from typing import Optional, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum


class CompatibilityLevel(Enum):
    """Level of compatibility between SQL and code pagination."""
    PERFECT = "perfect"  # Exact match
    COMPATIBLE = "compatible"  # Values can be produced by code
    INCOMPATIBLE = "incompatible"  # Values cannot be produced
    UNKNOWN = "unknown"  # Cannot determine (complex expressions)


@dataclass
class PaginationParams:
    """Pagination parameters extracted from SQL or code."""
    limit: Optional[int] = None
    offset: Optional[int] = None
    page_size: Optional[int] = None  # For Ruby code pagination logic
    has_limit: bool = False
    has_offset: bool = False


@dataclass
class PaginationMatch:
    """Result of comparing SQL and code pagination."""
    compatibility: CompatibilityLevel
    limit_match: bool
    offset_compatible: bool
    issues: list[str]
    details: Dict[str, Any]


class PaginationExtractor:
    """Extracts pagination parameters from SQL and Ruby code."""

    def extract_from_sql(self, sql: str) -> PaginationParams:
        """Extract LIMIT and OFFSET values from SQL query."""
        params = PaginationParams()

        # Extract LIMIT
        limit_match = re.search(r'\bLIMIT\s+(\d+)', sql, re.IGNORECASE)
        if limit_match:
            params.has_limit = True
            params.limit = int(limit_match.group(1))

        # Extract OFFSET
        offset_match = re.search(r'\bOFFSET\s+(\d+)', sql, re.IGNORECASE)
        if offset_match:
            params.has_offset = True
            params.offset = int(offset_match.group(1))

        return params

    def extract_from_ruby(self, code: str, constants: Optional[Dict[str, int]] = None) -> PaginationParams:
        """
        Extract pagination parameters from Ruby/Rails code.

        Args:
            code: Ruby code snippet
            constants: Optional dict of constant values (e.g., {"VC_PAGE_SIZE": 1000})
        """
        params = PaginationParams()
        constants = constants or {}

        # Find .limit() calls
        limit_match = re.search(r'\.limit\s*\(\s*([^)]+)\s*\)', code, re.IGNORECASE)
        if limit_match:
            params.has_limit = True
            limit_expr = limit_match.group(1).strip()
            params.limit = self._resolve_expression(limit_expr, constants)
            if params.limit:
                params.page_size = params.limit

        # Find .take, .first, .last (equivalent to LIMIT 1)
        # Pattern: .take or .take() or .take(n) or .first or .first() or .last or .last()
        if not params.has_limit:
            take_match = re.search(r'\.(take|first|last)\b(?:\s*\(\s*([^)]*)\s*\))?', code, re.IGNORECASE)
            if take_match:
                params.has_limit = True
                arg = take_match.group(2)
                if arg and arg.strip():
                    # .take(n) or .first(n)
                    params.limit = self._resolve_expression(arg.strip(), constants)
                else:
                    # .take, .first, .last without arguments = LIMIT 1
                    params.limit = 1
                if params.limit:
                    params.page_size = params.limit

        # Find .offset() calls
        offset_match = re.search(r'\.offset\s*\(\s*([^)]+)\s*\)', code, re.IGNORECASE)
        if offset_match:
            params.has_offset = True
            offset_expr = offset_match.group(1).strip()

            # Try to extract page size from offset expression
            # Common patterns: (page-1)*SIZE, page*SIZE, (n-1)*page_size
            page_size = self._extract_page_size_from_offset(offset_expr, constants)
            if page_size:
                params.page_size = page_size
                # Offset value depends on page number, so we can't determine a specific value
                # but we know the granularity

        return params

    def _resolve_expression(self, expr: str, constants: Dict[str, int]) -> Optional[int]:
        """
        Try to resolve a Ruby expression to an integer value.

        Handles:
        - Literals: "1000" → 1000
        - Constants: "VC_PAGE_SIZE" → 1000 (if in constants dict)
        - Simple arithmetic: "500 * 2" → 1000
        """
        expr = expr.strip()

        # Try direct integer conversion
        if expr.isdigit():
            return int(expr)

        # Try constant lookup
        if expr in constants:
            return constants[expr]

        # Try simple arithmetic with constants
        # Pattern: CONSTANT * number or number * CONSTANT
        arith_match = re.match(r'(\w+)\s*\*\s*(\d+)', expr)
        if arith_match:
            const_name = arith_match.group(1)
            multiplier = int(arith_match.group(2))
            if const_name in constants:
                return constants[const_name] * multiplier

        arith_match = re.match(r'(\d+)\s*\*\s*(\w+)', expr)
        if arith_match:
            multiplier = int(arith_match.group(1))
            const_name = arith_match.group(2)
            if const_name in constants:
                return multiplier * constants[const_name]

        # Cannot resolve
        return None

    def _extract_page_size_from_offset(self, offset_expr: str, constants: Dict[str, int]) -> Optional[int]:
        """
        Extract page size from offset expression like (page-1)*SIZE.

        Common patterns:
        - (page-1)*1000
        - (n-1)*VC_PAGE_SIZE
        - page*page_size
        """
        # Pattern: (variable - number) * SIZE
        match = re.search(r'\([^)]+\)\s*\*\s*([^)]+)', offset_expr)
        if match:
            size_expr = match.group(1).strip()
            return self._resolve_expression(size_expr, constants)

        # Pattern: variable * SIZE
        match = re.search(r'\w+\s*\*\s*([^)]+)', offset_expr)
        if match:
            size_expr = match.group(1).strip()
            return self._resolve_expression(size_expr, constants)

        return None


class PaginationMatcher:
    """Semantic matcher for pagination parameters."""

    def __init__(self):
        self.extractor = PaginationExtractor()

    def match(
        self,
        sql_params: PaginationParams,
        code_params: PaginationParams
    ) -> PaginationMatch:
        """
        Compare SQL and code pagination parameters.

        Returns detailed match result with compatibility level.
        """
        issues = []
        details = {}

        # Check LIMIT compatibility
        limit_match = self._check_limit(sql_params, code_params, issues, details)

        # Check OFFSET compatibility
        offset_compatible = self._check_offset(sql_params, code_params, issues, details)

        # Determine overall compatibility
        if not sql_params.has_limit and not sql_params.has_offset:
            compatibility = CompatibilityLevel.PERFECT
        elif limit_match and offset_compatible:
            compatibility = CompatibilityLevel.PERFECT
        elif (not sql_params.has_limit or limit_match) and (not sql_params.has_offset or offset_compatible):
            compatibility = CompatibilityLevel.COMPATIBLE
        elif issues:
            compatibility = CompatibilityLevel.INCOMPATIBLE
        else:
            compatibility = CompatibilityLevel.UNKNOWN

        return PaginationMatch(
            compatibility=compatibility,
            limit_match=limit_match,
            offset_compatible=offset_compatible,
            issues=issues,
            details=details
        )

    def _check_limit(
        self,
        sql_params: PaginationParams,
        code_params: PaginationParams,
        issues: list,
        details: dict
    ) -> bool:
        """Check if LIMIT values match."""
        if not sql_params.has_limit:
            return True  # No LIMIT required

        if not code_params.has_limit:
            issues.append("Code missing LIMIT")
            return False

        # Both have LIMIT - check values
        if sql_params.limit is None or code_params.limit is None:
            details["limit_check"] = "unknown"
            return True  # Unknown, give benefit of doubt

        if sql_params.limit == code_params.limit:
            details["limit_check"] = f"match ({sql_params.limit})"
            return True

        # Values don't match
        issues.append(f"LIMIT mismatch: SQL={sql_params.limit}, Code={code_params.limit}")
        details["limit_check"] = "mismatch"
        return False

    def _check_offset(
        self,
        sql_params: PaginationParams,
        code_params: PaginationParams,
        issues: list,
        details: dict
    ) -> bool:
        """
        Check if OFFSET is compatible.

        For code with pagination pattern (page-1)*size, SQL offset must be
        a multiple of the page size.
        """
        if not sql_params.has_offset:
            return True  # No OFFSET required

        if not code_params.has_offset:
            issues.append("Code missing OFFSET")
            return False

        # If we can't determine the page size, can't validate
        if code_params.page_size is None:
            details["offset_check"] = "unknown"
            return True  # Unknown, give benefit of doubt

        # SQL offset must be a multiple of the code's page size
        if sql_params.offset is None:
            details["offset_check"] = "unknown"
            return True

        if sql_params.offset % code_params.page_size == 0:
            page_num = (sql_params.offset // code_params.page_size) + 1
            details["offset_check"] = f"compatible (page {page_num})"
            return True

        # Offset is not achievable with this page size
        issues.append(
            f"OFFSET incompatible: SQL={sql_params.offset} is not a multiple of "
            f"page_size={code_params.page_size}"
        )
        details["offset_check"] = "incompatible"
        return False

    def match_sql_to_code(
        self,
        sql: str,
        code: str,
        constants: Optional[Dict[str, int]] = None
    ) -> PaginationMatch:
        """
        Convenience method to extract and match in one call.

        Args:
            sql: SQL query string
            code: Ruby code string
            constants: Optional dict of constant values
        """
        sql_params = self.extractor.extract_from_sql(sql)
        code_params = self.extractor.extract_from_ruby(code, constants)

        return self.match(sql_params, code_params)
