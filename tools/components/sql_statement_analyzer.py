"""
SQL Statement Analysis Utility

Centralized logic for extracting operation types, tables, and columns from SQL statements.
Eliminates duplication between enhanced_sql_rails_search and transaction_analyzer.
"""
from __future__ import annotations

import re
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class StatementInfo:
    """Information extracted from a SQL statement."""
    operation: str  # INSERT, SELECT, UPDATE, DELETE, BEGIN, COMMIT, etc.
    table: Optional[str]
    columns: List[str]
    raw_sql: str

    def is_dml(self) -> bool:
        """Check if statement is a data manipulation operation."""
        return self.operation in ('INSERT', 'UPDATE', 'DELETE', 'SELECT')

    def is_write(self) -> bool:
        """Check if statement modifies data."""
        return self.operation in ('INSERT', 'UPDATE', 'DELETE')

    def is_transaction_control(self) -> bool:
        """Check if statement is transaction control."""
        return self.operation in ('BEGIN', 'COMMIT', 'ROLLBACK')


class SQLStatementAnalyzer:
    """
    Analyzer for individual SQL statements to extract operation type, tables, and columns.

    Provides a single source of truth for SQL parsing used by both tools.
    """

    def __init__(self):
        pass

    def analyze(self, sql: str) -> StatementInfo:
        """
        Analyze a SQL statement and extract key information.

        Args:
            sql: Raw SQL statement (may include comments, formatting)

        Returns:
            StatementInfo with operation, table, and columns
        """
        operation = self.extract_operation(sql)
        table = self.extract_table(sql, operation)
        columns = self.extract_columns(sql, operation)

        return StatementInfo(
            operation=operation,
            table=table,
            columns=columns,
            raw_sql=sql
        )

    def extract_operation(self, sql: str) -> str:
        """
        Extract the main SQL operation type from a statement.

        Handles comments and various SQL dialects.

        Args:
            sql: Raw SQL statement

        Returns:
            Operation type: 'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'BEGIN', 'COMMIT', 'ROLLBACK', 'OTHER'
        """
        # Remove comments (both /* ... */ and -- ...)
        sql_no_comments = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        sql_no_comments = re.sub(r'--[^\n]*', '', sql_no_comments)

        sql_upper = sql_no_comments.upper().strip()

        # Check for each operation type
        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        elif sql_upper.startswith('BEGIN') or \
             sql_upper.startswith('START TRANSACTION') or \
             sql_upper.startswith('BEGIN TRANSACTION') or \
             sql_upper.startswith('BEGIN WORK'):
            return 'BEGIN'
        elif sql_upper.startswith('COMMIT'):
            return 'COMMIT'
        elif sql_upper.startswith('ROLLBACK'):
            return 'ROLLBACK'
        elif sql_upper.startswith('SET'):
            return 'SET'
        elif sql_upper.startswith('SHOW'):
            return 'SHOW'
        else:
            return 'OTHER'

    def extract_table(self, sql: str, operation: Optional[str] = None) -> Optional[str]:
        """
        Extract the primary table name from a SQL statement.

        Handles comments, backticks, and different SQL dialects.

        Args:
            sql: Raw SQL statement
            operation: Pre-computed operation type (optional, will extract if not provided)

        Returns:
            Table name or None if not found
        """
        if operation is None:
            operation = self.extract_operation(sql)

        # Remove comments and backticks
        sql_no_comments = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        sql_clean = re.sub(r'`', '', sql_no_comments)

        match = None

        if operation == 'INSERT':
            # INSERT INTO table (...) or INSERT INTO `table` (...)
            match = re.search(r'INSERT\s+INTO\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'SELECT':
            # SELECT ... FROM table or SELECT ... FROM `table`
            match = re.search(r'FROM\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'UPDATE':
            # UPDATE table SET ... or UPDATE `table` SET ...
            match = re.search(r'UPDATE\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'DELETE':
            # DELETE FROM table or DELETE FROM `table`
            match = re.search(r'FROM\s+(\w+)', sql_clean, re.IGNORECASE)
        else:
            return None

        return match.group(1) if match else None

    def extract_columns(self, sql: str, operation: Optional[str] = None) -> List[str]:
        """
        Extract column names from a SQL statement.

        Args:
            sql: Raw SQL statement
            operation: Pre-computed operation type (optional)

        Returns:
            List of column names (may be empty)
        """
        if operation is None:
            operation = self.extract_operation(sql)

        columns = []

        if operation == 'INSERT':
            columns = self._extract_insert_columns(sql)
        elif operation == 'UPDATE':
            columns = self._extract_update_columns(sql)
        elif operation == 'SELECT':
            columns = self._extract_select_columns(sql)

        return columns

    def _extract_insert_columns(self, sql: str) -> List[str]:
        """Extract columns from INSERT statement."""
        # Pattern: INSERT INTO table (col1, col2, col3) VALUES (...)
        insert_match = re.search(r'INSERT\s+INTO\s+["`]?\w+["`]?\s*\(([^)]+)\)', sql, re.IGNORECASE)

        if not insert_match:
            return []

        columns_str = insert_match.group(1)
        # Remove backticks, quotes, and split by comma
        columns = [col.strip().strip('"`') for col in columns_str.split(',')]

        return [col for col in columns if col]  # Filter empty strings

    def _extract_update_columns(self, sql: str) -> List[str]:
        """Extract columns from UPDATE statement."""
        # Pattern: UPDATE table SET col1 = val1, col2 = val2, ...
        set_match = re.search(r'SET\s+(.+?)(?:WHERE|$)', sql, re.IGNORECASE | re.DOTALL)

        if not set_match:
            return []

        set_clause = set_match.group(1)
        # Extract column names before '='
        column_matches = re.findall(r'(["`]?\w+["`]?)\s*=', set_clause)

        columns = [col.strip().strip('"`') for col in column_matches]

        return [col for col in columns if col]

    def _extract_select_columns(self, sql: str) -> List[str]:
        """Extract columns from SELECT statement."""
        # Pattern: SELECT col1, col2, col3 FROM ...
        # Handle SELECT * separately
        if re.search(r'SELECT\s+\*', sql, re.IGNORECASE):
            return ['*']

        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)

        if not select_match:
            return []

        columns_str = select_match.group(1)

        # Split by comma, but be careful with function calls like COUNT(*)
        # Simple approach: split and clean
        raw_columns = columns_str.split(',')
        columns = []

        for col in raw_columns:
            col = col.strip()
            # Remove aliases (AS something)
            col = re.sub(r'\s+AS\s+\w+', '', col, flags=re.IGNORECASE)
            # Extract column name from qualified names (table.column)
            col_match = re.search(r'(\w+)$', col)
            if col_match:
                columns.append(col_match.group(1))

        return [col for col in columns if col and col.lower() not in ('from', 'where', 'order', 'group')]

    def extract_signature_columns(self, sql: str) -> List[str]:
        """
        Extract distinctive column names from an INSERT query for fingerprinting.

        Filters out generic Rails timestamp columns that don't help identify code.

        Args:
            sql: INSERT statement SQL

        Returns:
            List of distinctive column names (without id, created_at, updated_at, deleted_at)
        """
        columns = self.extract_columns(sql, operation='INSERT')

        # Filter out columns that are auto-populated and don't appear in Ruby code
        generic_columns = {
            'id',           # Always auto-generated by database
            'created_at',   # Rails timestamp, auto-populated
            'updated_at',   # Rails timestamp, auto-populated
            'deleted_at'    # Paranoia gem, auto-populated
        }

        signature_columns = [col for col in columns if col.lower() not in generic_columns]

        return signature_columns

    def is_transaction_control(self, sql: str) -> bool:
        """Check if SQL is a transaction control statement."""
        operation = self.extract_operation(sql)
        return operation in ('BEGIN', 'COMMIT', 'ROLLBACK')

    def is_dml_statement(self, sql: str) -> bool:
        """Check if SQL is a data manipulation statement."""
        operation = self.extract_operation(sql)
        return operation in ('INSERT', 'SELECT', 'UPDATE', 'DELETE')
