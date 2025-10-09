"""
Adaptive SQL Log Extractor

Normalizes SQL statements from heterogeneous database logs so downstream tools
can operate on clean SQL. Designed to be used as a pre‑processor by tools like
`enhanced_sql_rails_search` and `transaction_analyzer`.

This module is intentionally self‑contained (no CLI) and safe to import.
"""
from __future__ import annotations

import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from collections import Counter, defaultdict


class Confidence(Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class SQLType(Enum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    ALTER = "ALTER"
    DROP = "DROP"
    TRANSACTION = "TRANSACTION"
    UNKNOWN = "UNKNOWN"


@dataclass
class ExtractedSQL:
    """Represents an extracted SQL statement with metadata."""
    sql: str
    sql_type: SQLType
    confidence: Confidence
    line_start: int
    line_end: int
    warnings: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    has_comments: bool = False
    looks_truncated: bool = False
    original_block: str = ""
    metadata_removed: str = ""
    validation_results: Dict[str, bool] = field(default_factory=dict)


@dataclass
class LogFormat:
    """Inferred log format characteristics used during extraction."""
    entry_patterns: List[str] = field(default_factory=list)
    sql_markers: Set[str] = field(default_factory=set)
    typical_prefix_length: int = 0
    continuation_indent: Optional[str] = None


class AdaptiveSQLExtractor:
    """Extractor that adapts to arbitrary DB log formats and returns clean SQL."""

    SQL_KEYWORDS = {
        'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'CREATE', 'ALTER', 'DROP',
        'TRUNCATE', 'MERGE', 'REPLACE', 'BEGIN', 'START', 'COMMIT', 'ROLLBACK',
        'SET', 'SHOW', 'DESCRIBE', 'EXPLAIN', 'ANALYZE', 'CALL', 'EXECUTE', 'WITH'
    }

    COMMON_MARKERS = {'Query', 'Execute', 'Statement', 'SQL', 'exec', 'run'}

    def __init__(self) -> None:
        self.learned_format: Optional[LogFormat] = None
        self.current_line_num: int = 0

    def extract_all_sql(self, log_text: str) -> List[ExtractedSQL]:
        """Main entry: extract all SQL statements from raw logs or plain SQL."""
        if not log_text:
            return []

        lines = log_text.split('\n')

        if self._looks_like_plain_sql(log_text):
            statements = self._extract_plain_sql(log_text)
        else:
            self.learned_format = self._learn_log_format(lines)
            statements = self._extract_statements(lines)

        for stmt in statements:
            self._validate_statement(stmt)
            self._add_intelligence(stmt)

        return statements

    # --------------------------- Detection helpers ---------------------------
    def _looks_like_plain_sql(self, text: str) -> bool:
        lines = text.strip().split('\n')
        if not lines:
            return False

        non_empty = [l.strip() for l in lines[:10] if l.strip()]
        if not non_empty:
            return False

        sql_line_count = 0
        log_line_count = 0
        for line in non_empty:
            if any(line.upper().startswith(kw) for kw in self.SQL_KEYWORDS):
                sql_line_count += 1
            if self._contains_timestamp_pattern(line) or any(m in line for m in self.COMMON_MARKERS):
                log_line_count += 1

        return sql_line_count > 0 and log_line_count == 0

    def _contains_timestamp_pattern(self, line: str) -> bool:
        patterns = [
            r'\d{4}[-/]\d{2}[-/]\d{2}',
            r'\d{2}:\d{2}:\d{2}',
            r'\d{10,13}',
            r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}',
        ]
        return any(re.search(p, line[:50]) for p in patterns)

    def _learn_log_format(self, lines: List[str]) -> LogFormat:
        fmt = LogFormat()
        sample = lines[: min(50, len(lines))]
        prefixes: List[str] = []
        for line in sample:
            pos = self._find_sql_start_position(line)
            if pos > 0:
                prefix = line[:pos].rstrip()
                prefixes.append(prefix)
                for marker in self.COMMON_MARKERS:
                    if marker in prefix:
                        fmt.sql_markers.add(marker)
        if prefixes:
            fmt.typical_prefix_length = sum(len(p) for p in prefixes) // len(prefixes)
        fmt.continuation_indent = self._detect_continuation_pattern(lines)
        return fmt

    def _find_sql_start_position(self, line: str) -> int:
        upper = line.upper()
        earliest = len(line)
        for keyword in self.SQL_KEYWORDS:
            m = re.search(r'\b' + re.escape(keyword) + r'\b', upper)
            if m and m.start() < earliest:
                earliest = m.start()
        for comment in ('--', '/*'):
            pos = line.find(comment)
            if pos >= 0 and pos < earliest:
                remaining = line[pos:]
                if any(kw in remaining.upper() for kw in self.SQL_KEYWORDS):
                    earliest = pos
        return earliest if earliest < len(line) else -1

    def _detect_continuation_pattern(self, lines: List[str]) -> Optional[str]:
        indents: List[str] = []
        for i in range(1, len(lines)):
            if not self._looks_like_new_entry(lines[i]):
                stripped = lines[i].lstrip()
                if stripped:
                    indent = lines[i][: len(lines[i]) - len(stripped)]
                    if indent:
                        indents.append(indent)
        if not indents:
            return None
        return Counter(indents).most_common(1)[0][0]

    def _looks_like_new_entry(self, line: str) -> bool:
        if not line.strip():
            return False
        if self.learned_format and self.learned_format.sql_markers:
            if any(marker in line for marker in self.learned_format.sql_markers):
                return True
        if self._contains_timestamp_pattern(line):
            return True
        sql_pos = self._find_sql_start_position(line)
        return sql_pos > 10

    # ------------------------------ Extraction ------------------------------
    def _extract_plain_sql(self, sql_text: str) -> List[ExtractedSQL]:
        statements: List[ExtractedSQL] = []
        current: List[str] = []
        in_string = False
        string_char: Optional[str] = None
        lines = sql_text.split('\n')
        start_line = 0

        for i, line in enumerate(lines):
            for idx, ch in enumerate(line):
                if not in_string and ch in ("'", '"'):
                    in_string = True
                    string_char = ch
                elif in_string and ch == string_char:
                    prev = line[idx - 1] if idx > 0 else ''
                    if prev != '\\':
                        in_string = False
            current.append(line)
            if not in_string and line.rstrip().endswith(';'):
                sql = '\n'.join(current)
                if sql.strip():
                    statements.append(self._create_statement([sql], start_line, i, ""))
                current = []
                start_line = i + 1

        if current:
            sql = '\n'.join(current)
            if sql.strip():
                statements.append(self._create_statement([sql], start_line, len(lines) - 1, ""))

        if not statements and sql_text.strip():
            statements.append(self._create_statement([sql_text.strip()], 0, len(lines) - 1, ""))

        return statements

    def _extract_statements(self, lines: List[str]) -> List[ExtractedSQL]:
        statements: List[ExtractedSQL] = []
        current_sql: List[str] = []
        current_metadata = ""
        start_line = -1
        in_sql = False
        in_transaction = False

        for i, raw_line in enumerate(lines):
            self.current_line_num = i
            line = raw_line.rstrip('\n')

            if self._looks_like_new_entry(line):
                sql_pos = self._find_sql_start_position(line)
                if sql_pos >= 0:
                    sql_part = line[sql_pos:]
                    metadata = line[:sql_pos].rstrip()

                    # Transaction boundaries
                    if self._is_transaction_start(sql_part):
                        if current_sql:
                            statements.append(self._create_statement(current_sql, start_line, i - 1, current_metadata))
                        current_sql = [sql_part]
                        current_metadata = metadata
                        start_line = i
                        in_sql = True
                        in_transaction = True
                    elif self._is_transaction_end(sql_part):
                        if in_transaction:
                            current_sql.append(sql_part)
                            statements.append(self._create_statement(current_sql, start_line, i, current_metadata))
                            current_sql = []
                            in_sql = False
                            in_transaction = False
                        else:
                            statements.append(self._create_statement([sql_part], i, i, metadata))
                    elif in_transaction:
                        current_sql.append(sql_part)
                    else:
                        # Regular statement outside transaction
                        if current_sql:
                            statements.append(self._create_statement(current_sql, start_line, i - 1, current_metadata))
                        current_sql = [sql_part]
                        current_metadata = metadata
                        start_line = i
                        in_sql = True
                else:
                    # Header line without SQL; nothing to do
                    if not in_transaction and current_sql:
                        statements.append(self._create_statement(current_sql, start_line, i - 1, current_metadata))
                        current_sql = []
                        in_sql = False
            elif in_sql or in_transaction:
                cleaned = self._clean_continuation_line(line)
                if cleaned:
                    current_sql.append(cleaned)

        if current_sql:
            statements.append(self._create_statement(current_sql, start_line, len(lines) - 1, current_metadata))

        return statements

    # ------------------------------ Utilities -------------------------------
    def _is_transaction_start(self, sql: str) -> bool:
        sql_upper = sql.upper().strip()
        starts = ['BEGIN', 'START TRANSACTION', 'BEGIN TRANSACTION', 'BEGIN WORK', 'START']
        for s in starts:
            if sql_upper.startswith(s):
                if 'BEGIN' in s and any(x in sql_upper for x in ['DECLARE', 'IF', 'WHILE', 'FOR']):
                    return False
                return True
        return False

    def _is_transaction_end(self, sql: str) -> bool:
        sql_upper = sql.upper().strip()
        ends = ['COMMIT', 'ROLLBACK', 'COMMIT WORK', 'ROLLBACK WORK', 'COMMIT TRANSACTION', 'ROLLBACK TRANSACTION']
        return any(sql_upper == e or sql_upper.startswith(e) for e in ends)

    def _looks_like_statement_complete(self, sql_lines: List[str]) -> bool:
        if not sql_lines:
            return False
        full_sql = '\n'.join(sql_lines)
        if full_sql.rstrip().endswith(';'):
            return True
        if full_sql.count('(') != full_sql.count(')'):
            return False
        if full_sql.count("'") % 2 != 0:
            return False
        last = sql_lines[-1].strip().upper()
        if any(last.endswith(end) for end in [')', 'END', 'COMMIT', 'ROLLBACK']):
            return True
        return False

    def _clean_continuation_line(self, line: str) -> str:
        if self.learned_format and self.learned_format.continuation_indent:
            if line.startswith(self.learned_format.continuation_indent):
                return line
        if not any(line.lstrip().upper().startswith(kw) for kw in self.SQL_KEYWORDS):
            return line
        return line

    def _create_statement(self, sql_lines: List[str], start: int, end: int, metadata: str) -> ExtractedSQL:
        sql_text = '\n'.join(sql_lines)
        sql_type = self._determine_sql_type(sql_text)
        confidence = Confidence.MEDIUM
        warnings: List[str] = []
        looks_truncated = self._check_truncation(sql_text)
        if looks_truncated:
            warnings.append("SQL may be truncated or incomplete")
            confidence = Confidence.NEEDS_REVIEW
        has_comments = ('--' in sql_text) or ('/*' in sql_text)
        return ExtractedSQL(
            sql=sql_text,
            sql_type=sql_type,
            confidence=confidence,
            line_start=start + 1,
            line_end=end + 1,
            warnings=warnings,
            has_comments=has_comments,
            looks_truncated=looks_truncated,
            metadata_removed=metadata,
        )

    def _determine_sql_type(self, sql: str) -> SQLType:
        sql_upper = self._remove_comments(sql).lstrip().upper()
        mapping = {
            'SELECT': SQLType.SELECT,
            'INSERT': SQLType.INSERT,
            'UPDATE': SQLType.UPDATE,
            'DELETE': SQLType.DELETE,
            'CREATE': SQLType.CREATE,
            'ALTER': SQLType.ALTER,
            'DROP': SQLType.DROP,
            'BEGIN': SQLType.TRANSACTION,
            'START TRANSACTION': SQLType.TRANSACTION,
            'COMMIT': SQLType.TRANSACTION,
            'ROLLBACK': SQLType.TRANSACTION,
        }
        for key, val in mapping.items():
            if sql_upper.startswith(key):
                return val
        return SQLType.UNKNOWN

    def _remove_comments(self, sql: str) -> str:
        sql = re.sub(r'--.*$', '', sql, flags=re.MULTILINE)
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        return sql

    def _check_truncation(self, sql: str) -> bool:
        sql_clean = self._remove_comments(sql).rstrip()
        if not sql_clean.endswith(';'):
            if not any(sql_clean.upper().endswith(cmd) for cmd in ['COMMIT', 'ROLLBACK']):
                incomplete = [
                    r'WHERE\s*$', r'AND\s*$', r'OR\s*$', r'VALUES\s*\(\s*$', r'SET\s*$',
                    r'FROM\s*$', r'JOIN\s*$', r',\s*$'
                ]
                if any(re.search(p, sql_clean, re.IGNORECASE) for p in incomplete):
                    return True
        if sql_clean.count('(') != sql_clean.count(')'):
            return True
        if (sql_clean.count("'") % 2 != 0) or (sql_clean.count('"') % 2 != 0):
            return True
        return False

    def _validate_statement(self, stmt: ExtractedSQL) -> None:
        validations = {
            'balanced_parentheses': stmt.sql.count('(') == stmt.sql.count(')'),
            'balanced_quotes': (stmt.sql.count("'") % 2 == 0),
            'has_ending': stmt.sql.rstrip().endswith(';') or stmt.sql_type == SQLType.TRANSACTION,
            'not_empty': len(stmt.sql.strip()) > 0,
        }
        stmt.validation_results = validations
        if all(validations.values()) and stmt.confidence == Confidence.MEDIUM:
            stmt.confidence = Confidence.HIGH
        elif not all(validations.values()):
            if not validations['balanced_parentheses']:
                stmt.warnings.append('Unbalanced parentheses detected')
            if not validations['balanced_quotes']:
                stmt.warnings.append('Unbalanced quotes detected')
            stmt.confidence = Confidence.NEEDS_REVIEW

    def _add_intelligence(self, stmt: ExtractedSQL) -> None:
        sql_upper = stmt.sql.upper()
        if stmt.sql_type == SQLType.SELECT:
            if '(SELECT' in sql_upper:
                stmt.notes.append('Contains subquery')
            if any(j in sql_upper for j in ['LEFT JOIN', 'INNER JOIN', 'RIGHT JOIN', 'JOIN']):
                stmt.notes.append('Contains JOIN operations')
        elif stmt.sql_type == SQLType.INSERT:
            values_count = sql_upper.count('VALUES')
            if values_count > 1 or '),(' in stmt.sql:
                stmt.notes.append('Bulk INSERT detected')

