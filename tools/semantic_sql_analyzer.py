"""
Semantic SQL Analyzer - True AST-based SQL analysis for Rails code tracing.

Uses SQLGlot for proper SQL parsing and builds semantic understanding
through Rails conventions and query intent recognition.
"""
from __future__ import annotations

import sqlglot
from sqlglot import exp
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(Enum):
    """Semantic intent of SQL queries."""
    EXISTENCE_CHECK = "existence_check"
    COUNT_AGGREGATE = "count_aggregate"
    DATA_RETRIEVAL = "data_retrieval"
    DATA_INSERTION = "data_insertion"
    DATA_UPDATE = "data_update"
    DATA_DELETION = "data_deletion"
    TRANSACTION_CONTROL = "transaction_control"
    SCHEMA_OPERATION = "schema_operation"


@dataclass
class TableReference:
    """Represents a table reference in the query."""
    name: str
    alias: Optional[str] = None
    schema: Optional[str] = None

    @property
    def rails_model(self) -> str:
        """Convert table name to Rails model name."""
        return self._table_to_model(self.name)

    def _table_to_model(self, table: str) -> str:
        """Convert table name to Rails model name using proper pluralization."""
        # Remove any schema prefix
        table = table.split('.')[-1]
        table = table.lower()

        # Basic pluralization rules
        if table.endswith("ies"):
            singular = table[:-3] + "y"
        elif table.endswith("ses"):
            singular = table[:-2]
        elif table.endswith("es") and not table.endswith("oses"):
            singular = table[:-2]
        elif table.endswith("s"):
            singular = table[:-1]
        else:
            singular = table

        # Convert to CamelCase
        return "".join(word.capitalize() for word in singular.split("_"))


@dataclass
class ColumnReference:
    """Represents a column reference with context."""
    name: str
    table: Optional[str] = None
    alias: Optional[str] = None

    @property
    def is_foreign_key(self) -> bool:
        """Check if this column appears to be a foreign key."""
        return self.name.endswith("_id")

    @property
    def association_name(self) -> str:
        """Get the likely Rails association name for foreign keys."""
        if self.is_foreign_key:
            return self.name[:-3]  # Remove "_id"
        return self.name


@dataclass
class WhereCondition:
    """Represents a WHERE clause condition."""
    column: ColumnReference
    operator: str
    value_type: str  # 'parameter', 'literal', 'column', 'subquery'
    value: Any = None

    @property
    def is_parameterized(self) -> bool:
        """Check if this condition uses parameters."""
        return self.value_type == 'parameter'


@dataclass
class QueryAnalysis:
    """Complete semantic analysis of a SQL query."""
    raw_sql: str
    intent: QueryIntent
    tables: List[TableReference] = field(default_factory=list)
    columns: List[ColumnReference] = field(default_factory=list)
    where_conditions: List[WhereCondition] = field(default_factory=list)
    joins: List[Dict[str, Any]] = field(default_factory=list)
    aggregations: List[str] = field(default_factory=list)
    subqueries: List['QueryAnalysis'] = field(default_factory=list)
    has_limit: bool = False
    has_order: bool = False
    complexity: str = "low"
    rails_patterns: List[str] = field(default_factory=list)

    @property
    def primary_table(self) -> Optional[TableReference]:
        """Get the primary table being queried."""
        return self.tables[0] if self.tables else None

    @property
    def primary_model(self) -> Optional[str]:
        """Get the primary Rails model."""
        return self.primary_table.rails_model if self.primary_table else None


class SemanticSQLAnalyzer:
    """Semantic SQL analyzer using AST parsing and Rails conventions."""

    def __init__(self):
        self.parser = sqlglot

    def analyze(self, sql: str) -> QueryAnalysis:
        """Perform complete semantic analysis of SQL query."""
        try:
            # Parse SQL into AST - try MySQL first (backticks), then PostgreSQL
            try:
                parsed = self.parser.parse(sql, dialect="mysql")[0]
            except:
                parsed = self.parser.parse(sql, dialect="postgres")[0]

            # Build semantic analysis
            analysis = QueryAnalysis(raw_sql=sql, intent=QueryIntent.DATA_RETRIEVAL)

            # Extract components
            self._extract_tables(parsed, analysis)
            self._extract_columns(parsed, analysis)
            self._extract_where_conditions(parsed, analysis)
            self._extract_joins(parsed, analysis)
            self._analyze_intent(parsed, analysis)
            self._assess_complexity(parsed, analysis)
            self._infer_rails_patterns(analysis)

            return analysis

        except Exception as e:
            # Fallback for unparseable SQL
            return self._create_fallback_analysis(sql, str(e))

    def _extract_tables(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Extract table references from the query."""
        for table in parsed.find_all(exp.Table):
            table_ref = TableReference(
                name=table.name,
                alias=table.alias if hasattr(table, 'alias') else None,
                schema=table.db if hasattr(table, 'db') else None
            )
            analysis.tables.append(table_ref)

    def _extract_columns(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Extract column references from the query."""
        for column in parsed.find_all(exp.Column):
            col_ref = ColumnReference(
                name=column.name,
                table=column.table if hasattr(column, 'table') else None,
                alias=column.alias if hasattr(column, 'alias') else None
            )
            analysis.columns.append(col_ref)

    def _extract_where_conditions(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Extract WHERE clause conditions."""
        where = parsed.find(exp.Where)
        if not where:
            return

        # Find all binary operations in WHERE clause
        for binary_op in where.find_all(exp.Binary):
            if isinstance(binary_op.left, exp.Column):
                column = ColumnReference(
                    name=binary_op.left.name,
                    table=binary_op.left.table
                )

                # Determine value type
                value_type = "literal"
                value = None

                if isinstance(binary_op.right, exp.Parameter):
                    value_type = "parameter"
                    value = binary_op.right.this
                elif isinstance(binary_op.right, exp.Literal):
                    value_type = "literal"
                    value = binary_op.right.this
                elif isinstance(binary_op.right, exp.Column):
                    value_type = "column"
                    value = binary_op.right.name

                condition = WhereCondition(
                    column=column,
                    operator=binary_op.key,
                    value_type=value_type,
                    value=value
                )
                analysis.where_conditions.append(condition)

    def _extract_joins(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Extract JOIN information."""
        for join in parsed.find_all(exp.Join):
            join_info = {
                "type": join.kind if hasattr(join, 'kind') else "INNER",
                "table": join.this.name if hasattr(join.this, 'name') else str(join.this),
                "condition": str(join.on) if hasattr(join, 'on') else None
            }
            analysis.joins.append(join_info)

    def _analyze_intent(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Determine the semantic intent of the query."""

        # Check for SELECT 1 existence checks
        if isinstance(parsed, exp.Select):
            expressions = parsed.expressions

            # Look for SELECT 1 or SELECT 1 AS one patterns
            if len(expressions) == 1:
                expr = expressions[0]
                if isinstance(expr, exp.Literal) and str(expr.this) == "1":
                    analysis.intent = QueryIntent.EXISTENCE_CHECK
                elif (isinstance(expr, exp.Alias) and
                      isinstance(expr.this, exp.Literal) and
                      str(expr.this.this) == "1"):
                    analysis.intent = QueryIntent.EXISTENCE_CHECK

            # Alternative existence check: SELECT 1 FROM table WHERE... LIMIT 1
            if (len(expressions) == 1 and
                isinstance(expressions[0], exp.Literal) and
                str(expressions[0].this) == "1" and
                analysis.has_limit and
                analysis.where_conditions):
                analysis.intent = QueryIntent.EXISTENCE_CHECK

            # Look for COUNT aggregations - only pure COUNT queries
            count_found = False
            for expr in expressions:
                if isinstance(expr, exp.Count) or (isinstance(expr, exp.Alias) and isinstance(expr.this, exp.Count)):
                    count_found = True
                    analysis.aggregations.append("COUNT")

            # Only classify as COUNT_AGGREGATE if it's a pure count query (single expression)
            if count_found and len(expressions) == 1:
                analysis.intent = QueryIntent.COUNT_AGGREGATE

            # Check for LIMIT (common in existence checks)
            if parsed.find(exp.Limit):
                analysis.has_limit = True
                # Don't override data_retrieval intent just because of LIMIT
                # Only override if it's clearly a SELECT 1 existence check

            # Check for ORDER BY
            if parsed.find(exp.Order):
                analysis.has_order = True

        # Handle other statement types
        elif isinstance(parsed, exp.Insert):
            analysis.intent = QueryIntent.DATA_INSERTION
        elif isinstance(parsed, exp.Update):
            analysis.intent = QueryIntent.DATA_UPDATE
        elif isinstance(parsed, exp.Delete):
            analysis.intent = QueryIntent.DATA_DELETION
        elif isinstance(parsed, exp.Transaction):
            analysis.intent = QueryIntent.TRANSACTION_CONTROL
        # Handle transaction control statements - check raw SQL first
        elif sql.strip().upper().startswith(('BEGIN', 'COMMIT', 'ROLLBACK')):
            analysis.intent = QueryIntent.TRANSACTION_CONTROL

    def _assess_complexity(self, parsed: exp.Expression, analysis: QueryAnalysis) -> None:
        """Assess query complexity."""
        complexity_score = 0

        # Multiple tables
        if len(analysis.tables) > 1:
            complexity_score += 2

        # Joins
        if analysis.joins:
            complexity_score += len(analysis.joins)

        # Subqueries
        subquery_count = len(list(parsed.find_all(exp.Select))) - 1  # Subtract main query
        if subquery_count > 0:
            complexity_score += subquery_count * 2

        # Multiple WHERE conditions
        if len(analysis.where_conditions) > 1:
            complexity_score += 1

        # Aggregations
        if analysis.aggregations:
            complexity_score += 1

        # Set complexity level
        if complexity_score >= 5:
            analysis.complexity = "high"
        elif complexity_score >= 2:
            analysis.complexity = "medium"
        else:
            analysis.complexity = "low"

    def _infer_rails_patterns(self, analysis: QueryAnalysis) -> None:
        """Infer likely Rails/ActiveRecord patterns."""
        if not analysis.primary_model:
            return

        model = analysis.primary_model
        patterns = []

        # Existence check patterns
        if analysis.intent == QueryIntent.EXISTENCE_CHECK:
            if analysis.where_conditions:
                for condition in analysis.where_conditions:
                    if condition.is_parameterized:
                        col = condition.column.name
                        patterns.extend([
                            f"{model}.exists?({col}: value)",
                            f"{model}.where({col}: value).exists?",
                            f"{model}.find_by({col}: value).present?"
                        ])

                        # Association patterns for foreign keys
                        if condition.column.is_foreign_key:
                            assoc = condition.column.association_name
                            patterns.extend([
                                f"@{assoc}.{analysis.primary_table.name}.exists?",
                                f"current_{assoc}.{analysis.primary_table.name}.any?",
                                f"{assoc}.{model.lower()}s.exists?"
                            ])
            else:
                patterns.extend([
                    f"{model}.exists?",
                    f"{model}.any?",
                    f"!{model}.empty?"
                ])

        # Count patterns
        elif analysis.intent == QueryIntent.COUNT_AGGREGATE:
            patterns.extend([
                f"{model}.count",
                f"{model}.size",
                f"association.count"
            ])

            if analysis.where_conditions:
                patterns.append(f"{model}.where(...).count")

        # Data retrieval patterns
        elif analysis.intent == QueryIntent.DATA_RETRIEVAL:
            base_patterns = [f"{model}.all"]

            if analysis.where_conditions:
                base_patterns.extend([
                    f"{model}.where(...)",
                    f"{model}.find_by(...)",
                    f"association.where(...)"
                ])

            if analysis.has_order:
                base_patterns.append(f"{model}.order(...)")

            if analysis.has_limit:
                base_patterns.extend([f"{model}.limit(...)", f"{model}.first", f"{model}.last"])

            patterns.extend(base_patterns)

        # CRUD patterns
        elif analysis.intent == QueryIntent.DATA_INSERTION:
            patterns.extend([
                f"{model}.create(...)",
                f"{model}.new(...).save",
                f"build_{analysis.primary_table.name[:-1]}(...)"
            ])

        elif analysis.intent == QueryIntent.DATA_UPDATE:
            patterns.extend([
                f"{model}.update(...)",
                f"@{analysis.primary_table.name[:-1]}.save",
                f"{model}.update_all(...)"
            ])

        analysis.rails_patterns = patterns

    def _create_fallback_analysis(self, sql: str, error: str) -> QueryAnalysis:
        """Create basic analysis when SQL parsing fails."""
        analysis = QueryAnalysis(raw_sql=sql, intent=QueryIntent.DATA_RETRIEVAL)
        analysis.complexity = "unknown"

        # Try basic regex extraction as fallback
        import re

        # Extract table names
        table_matches = re.findall(r'FROM\s+["`]?(\w+)["`]?', sql, re.IGNORECASE)
        for table_name in table_matches:
            analysis.tables.append(TableReference(name=table_name.lower()))

        # Basic intent detection
        if re.search(r'SELECT\s+1\s+AS\s+one', sql, re.IGNORECASE):
            analysis.intent = QueryIntent.EXISTENCE_CHECK
        elif re.search(r'SELECT\s+COUNT\s*\(', sql, re.IGNORECASE):
            analysis.intent = QueryIntent.COUNT_AGGREGATE
        elif sql.strip().upper().startswith('INSERT'):
            analysis.intent = QueryIntent.DATA_INSERTION
        elif sql.strip().upper().startswith('UPDATE'):
            analysis.intent = QueryIntent.DATA_UPDATE

        return analysis


def create_fingerprint(analysis: QueryAnalysis) -> str:
    """Create a normalized fingerprint of the analyzed query."""
    if analysis.intent == QueryIntent.EXISTENCE_CHECK:
        table = analysis.primary_table.name if analysis.primary_table else "table"
        base = f"SELECT 1 AS one FROM {table}"

        if analysis.where_conditions:
            where_parts = []
            for condition in analysis.where_conditions:
                where_parts.append(f"{condition.column.name} {condition.operator} ?")
            base += f" WHERE {' AND '.join(where_parts)}"

        if analysis.has_limit:
            base += " LIMIT 1"
        return base

    elif analysis.intent == QueryIntent.COUNT_AGGREGATE:
        table = analysis.primary_table.name if analysis.primary_table else "table"
        base = f"SELECT COUNT(*) FROM {table}"

        if analysis.where_conditions:
            where_parts = []
            for condition in analysis.where_conditions:
                where_parts.append(f"{condition.column.name} {condition.operator} ?")
            base += f" WHERE {' AND '.join(where_parts)}"
        return base

    elif analysis.intent == QueryIntent.DATA_INSERTION:
        table = analysis.primary_table.name if analysis.primary_table else "table"
        return f"INSERT INTO {table} (...)"

    elif analysis.intent == QueryIntent.DATA_UPDATE:
        table = analysis.primary_table.name if analysis.primary_table else "table"
        base = f"UPDATE {table} SET ..."
        if analysis.where_conditions:
            where_parts = []
            for condition in analysis.where_conditions:
                where_parts.append(f"{condition.column.name} {condition.operator} ?")
            base += f" WHERE {' AND '.join(where_parts)}"
        return base

    elif analysis.intent == QueryIntent.DATA_DELETION:
        table = analysis.primary_table.name if analysis.primary_table else "table"
        base = f"DELETE FROM {table}"
        if analysis.where_conditions:
            where_parts = []
            for condition in analysis.where_conditions:
                where_parts.append(f"{condition.column.name} {condition.operator} ?")
            base += f" WHERE {' AND '.join(where_parts)}"
        return base

    # Default data retrieval fingerprint
    table = analysis.primary_table.name if analysis.primary_table else "table"
    base = f"SELECT * FROM {table}"

    if analysis.where_conditions:
        where_parts = []
        for condition in analysis.where_conditions:
            where_parts.append(f"{condition.column.name} {condition.operator} ?")
        base += f" WHERE {' AND '.join(where_parts)}"

    return base


def generate_verification_command(analysis: QueryAnalysis) -> Optional[str]:
    """Generate Rails console command to verify the query hypothesis."""
    if not analysis.primary_model:
        return None

    model = analysis.primary_model

    if analysis.intent == QueryIntent.EXISTENCE_CHECK:
        if analysis.where_conditions:
            condition = analysis.where_conditions[0]
            col = condition.column.name
            if condition.column.is_foreign_key:
                return f"rails runner 'puts {model}.exists?({col}: 1)'"
            else:
                return f"rails runner 'puts {model}.exists?({col}: \"test_value\")'"
        else:
            return f"rails runner 'puts {model}.exists?'"

    elif analysis.intent == QueryIntent.COUNT_AGGREGATE:
        if analysis.where_conditions:
            return f"rails runner 'puts {model}.where({analysis.where_conditions[0].column.name}: \"test\").count'"
        else:
            return f"rails runner 'puts {model}.count'"

    elif analysis.intent == QueryIntent.DATA_INSERTION:
        return f"rails runner 'puts {model}.new.save'"

    elif analysis.intent == QueryIntent.DATA_UPDATE:
        return f"rails runner 'puts {model}.update_all(updated_at: Time.current)'"

    else:
        # Default data retrieval
        if analysis.where_conditions:
            condition = analysis.where_conditions[0]
            return f"rails runner 'puts {model}.where({condition.column.name}: \"test\").to_sql'"
        else:
            return f"rails runner 'puts {model}.all.to_sql'"