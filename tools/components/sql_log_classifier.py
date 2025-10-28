"""
SQL Log Classification Utility

Centralized logic for classifying SQL inputs as single queries vs. transaction logs.
Eliminates duplication between enhanced_sql_rails_search and transaction_analyzer.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Optional
from dataclasses import dataclass

from .sql_log_extractor import AdaptiveSQLExtractor, SQLType


class SQLInputType(Enum):
    """Classification of SQL input types."""
    SINGLE_QUERY = "single_query"
    TRANSACTION_LOG = "transaction_log"
    EMPTY = "empty"
    UNRECOGNIZED = "unrecognized"


@dataclass
class ClassificationResult:
    """Result of SQL input classification."""
    input_type: SQLInputType
    query_count: int
    confidence: str  # "high", "medium", "low"
    reason: str

    def is_transaction(self) -> bool:
        """Check if input is a transaction log."""
        return self.input_type == SQLInputType.TRANSACTION_LOG

    def is_single_query(self) -> bool:
        """Check if input is a single query."""
        return self.input_type == SQLInputType.SINGLE_QUERY


class SQLLogClassifier:
    """
    Classifier for SQL inputs to determine if they are single queries or transaction logs.

    Used at the orchestration layer to route inputs to the appropriate tool:
    - Single queries → enhanced_sql_rails_search
    - Transaction logs → transaction_analyzer
    """

    def __init__(self):
        self.extractor = AdaptiveSQLExtractor()

    def classify(self, sql_input: str) -> ClassificationResult:
        """
        Classify SQL input as single query or transaction log.

        Args:
            sql_input: Raw SQL text (may include log timestamps, multiple queries, etc.)

        Returns:
            ClassificationResult with type, query count, and reasoning
        """
        if not sql_input or not sql_input.strip():
            return ClassificationResult(
                input_type=SQLInputType.EMPTY,
                query_count=0,
                confidence="high",
                reason="Empty input"
            )

        # Try extracting with AdaptiveSQLExtractor first (most reliable)
        try:
            extracted = self.extractor.extract_all_sql(sql_input)

            if not extracted:
                # Extractor found nothing, fall back to heuristic detection
                return self._classify_with_heuristics(sql_input)

            # Check if transaction type was detected
            if any(stmt.sql_type == SQLType.TRANSACTION for stmt in extracted):
                return ClassificationResult(
                    input_type=SQLInputType.TRANSACTION_LOG,
                    query_count=len(extracted),
                    confidence="high",
                    reason="Transaction block detected by SQL extractor"
                )

            # Multiple independent statements = transaction log
            if len(extracted) > 1:
                return ClassificationResult(
                    input_type=SQLInputType.TRANSACTION_LOG,
                    query_count=len(extracted),
                    confidence="high",
                    reason=f"Multiple SQL statements detected ({len(extracted)} queries)"
                )

            # Single statement extracted
            if len(extracted) == 1:
                return ClassificationResult(
                    input_type=SQLInputType.SINGLE_QUERY,
                    query_count=1,
                    confidence="high",
                    reason="Single SQL statement extracted"
                )

        except Exception as e:
            # Extractor failed, fall back to heuristics
            return self._classify_with_heuristics(sql_input)

    def _classify_with_heuristics(self, sql_input: str) -> ClassificationResult:
        """
        Fallback classification using heuristic pattern matching.

        Used when AdaptiveSQLExtractor fails or finds nothing.
        """
        lines = sql_input.strip().split('\n')

        # Look for timestamp patterns typical of MySQL general log
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+\d+\s+\w+'
        log_lines = sum(1 for line in lines if re.match(timestamp_pattern, line.strip()))

        # If we have multiple timestamped entries, it's likely a transaction log
        if log_lines >= 3:
            return ClassificationResult(
                input_type=SQLInputType.TRANSACTION_LOG,
                query_count=log_lines,
                confidence="medium",
                reason=f"Detected {log_lines} timestamped log entries"
            )

        # Check for explicit transaction boundaries
        has_begin = any('BEGIN' in line.upper() for line in lines)
        has_commit = any('COMMIT' in line.upper() for line in lines)

        # Count SQL operations
        sql_ops = ['SELECT', 'INSERT', 'UPDATE', 'DELETE']
        query_count = sum(
            1 for line in lines
            if any(op in line.upper() for op in sql_ops)
        )

        # Transaction markers + multiple queries = transaction log
        if has_begin and has_commit and query_count >= 2:
            return ClassificationResult(
                input_type=SQLInputType.TRANSACTION_LOG,
                query_count=query_count,
                confidence="medium",
                reason=f"BEGIN/COMMIT markers with {query_count} queries"
            )

        # Multiple queries without transaction markers = likely transaction log
        if query_count >= 3:
            return ClassificationResult(
                input_type=SQLInputType.TRANSACTION_LOG,
                query_count=query_count,
                confidence="low",
                reason=f"Multiple SQL operations detected ({query_count}), but no clear transaction markers"
            )

        # Single query detected
        if query_count == 1:
            return ClassificationResult(
                input_type=SQLInputType.SINGLE_QUERY,
                query_count=1,
                confidence="medium",
                reason="Single SQL operation detected"
            )

        # Unrecognized format
        return ClassificationResult(
            input_type=SQLInputType.UNRECOGNIZED,
            query_count=0,
            confidence="low",
            reason="Could not parse SQL input"
        )

    def should_use_transaction_analyzer(self, sql_input: str) -> bool:
        """
        Quick check: should this input be routed to transaction_analyzer?

        Convenience method for orchestration layer.
        """
        result = self.classify(sql_input)
        return result.is_transaction()

    def should_use_single_query_tool(self, sql_input: str) -> bool:
        """
        Quick check: should this input be routed to enhanced_sql_rails_search?

        Convenience method for orchestration layer.
        """
        result = self.classify(sql_input)
        return result.is_single_query()
