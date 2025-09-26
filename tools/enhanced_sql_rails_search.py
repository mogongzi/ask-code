"""
Intelligent SQL → Rails Code Detective

An AI-powered tool that reasons about SQL queries semantically to trace them back
to Rails source code. Handles complex patterns, transactions, and dynamic queries
through intelligent analysis rather than rigid pattern matching.

Uses SQLGlot AST parsing for true semantic understanding.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .base_tool import BaseTool
from .semantic_sql_analyzer import (
    SemanticSQLAnalyzer,
    QueryAnalysis,
    QueryIntent,
    create_fingerprint,
    generate_verification_command
)


@dataclass
class SQLMatch:
    """Represents a single match between SQL and Rails code."""
    path: str
    line: int
    snippet: str
    why: List[str]
    confidence: str
    match_type: str  # 'definition' or 'usage'


class EnhancedSQLRailsSearch(BaseTool):
    """Intelligent SQL to Rails code search using semantic analysis."""

    def __init__(self, project_root: Optional[str] = None):
        super().__init__(project_root)
        self.analyzer = SemanticSQLAnalyzer()

    @property
    def name(self) -> str:
        return "enhanced_sql_rails_search"

    @property
    def description(self) -> str:
        return (
            "Intelligently trace SQL queries back to Rails source code using "
            "semantic analysis, Rails conventions, and adaptive search strategies."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "Raw SQL query to trace"},
                "include_usage_sites": {
                    "type": "boolean",
                    "description": "Include where the query gets executed (views, controllers)",
                    "default": True
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return",
                    "default": 10
                }
            },
            "required": ["sql"],
        }

    async def execute(self, input_params: Dict[str, Any]) -> Any:
        self._debug_input(input_params)

        if not self.validate_input(input_params):
            error_result = {"error": "Invalid input"}
            self._debug_output(error_result)
            return error_result

        sql = input_params.get("sql", "").strip()
        self._debug_log("🔍 SQL Query", sql)
        include_usage = bool(input_params.get("include_usage_sites", True))
        max_results = int(input_params.get("max_results", 10))

        if not sql:
            error_result = {"error": "Empty SQL query"}
            self._debug_output(error_result)
            return error_result

        # Check if this is a transaction log
        if self._is_transaction_log(sql):
            error_result = {
                "error": "Transaction log detected. Use transaction_analyzer tool instead.",
                "suggestion": "This appears to be a complete transaction log with multiple queries. Use the transaction_analyzer tool to analyze the entire transaction flow and find related source code.",
                "detected_queries": self._count_queries_in_log(sql)
            }
            self._debug_output(error_result)
            return error_result

        if not self.project_root or not Path(self.project_root).exists():
            error_result = {"error": "Project root not found"}
            self._debug_output(error_result)
            return error_result

        # Perform semantic analysis
        analysis = self.analyzer.analyze(sql)
        self._debug_log("🧠 SQL Analysis", {
            "intent": analysis.intent.value,
            "primary_model": analysis.primary_model,
            "tables": [t.name for t in analysis.tables],
            "complexity": analysis.complexity,
            "rails_patterns": analysis.rails_patterns
        })

        # Create fingerprint
        fingerprint = create_fingerprint(analysis)
        self._debug_log("🔑 Query Fingerprint", fingerprint)

        # Find definition sites using intelligent strategies
        self._debug_log("🔎 Starting definition search with strategies")
        definition_matches = await self._find_definition_sites_semantic(analysis)
        self._debug_log("📍 Definition matches found", len(definition_matches))

        # Find usage sites
        usage_matches = []
        if include_usage and definition_matches:
            self._debug_log("🔍 Finding usage sites for matches")
            usage_matches = await self._find_usage_sites(definition_matches)
            self._debug_log("📍 Usage matches found", len(usage_matches))

        # Combine and rank matches
        all_matches = definition_matches + usage_matches
        self._debug_log("🏆 Ranking matches", f"{len(all_matches)} total matches")
        ranked_matches = self._rank_matches(all_matches, analysis)[:max_results]
        self._debug_log("✅ Final ranked matches", len(ranked_matches))

        # Generate verification command
        verify_cmd = generate_verification_command(analysis)

        result = {
            "fingerprint": fingerprint,
            "matches": [
                {
                    "path": match.path,
                    "line": match.line,
                    "snippet": match.snippet,
                    "why": match.why,
                    "confidence": match.confidence
                }
                for match in ranked_matches
            ],
            "verify": verify_cmd,
            "sql_analysis": {
                "intent": analysis.intent.value,
                "tables": [t.name for t in analysis.tables],
                "models": [t.rails_model for t in analysis.tables],
                "complexity": analysis.complexity,
                "rails_patterns": analysis.rails_patterns,
                "where_conditions": len(analysis.where_conditions),
                "has_joins": bool(analysis.joins)
            }
        }

        self._debug_output(result)
        return result

    def _parse_sql_query(self, sql: str) -> Dict[str, Any]:
        """Semantically analyze SQL query to understand intent and structure."""
        sql_clean = re.sub(r'\s+', ' ', sql.strip())
        sql_upper = sql_clean.upper()

        # Determine query intent
        intent = self._analyze_query_intent(sql_clean, sql_upper)

        # Extract structural components
        tables = self._extract_tables(sql_upper)
        columns = self._extract_select_columns(sql_upper)
        where_info = self._extract_where_conditions(sql_upper, sql_clean)
        joins = self._extract_joins(sql_upper)
        subqueries = self._detect_subqueries(sql_clean)

        # Infer Rails patterns
        models = [self._table_to_model(t) for t in tables if t]
        rails_patterns = self._infer_rails_patterns(intent, tables, where_info, columns, sql_upper)

        return {
            "original": sql,
            "intent": intent,
            "tables": tables,
            "models": models,
            "columns": columns,
            "where_info": where_info,
            "joins": joins,
            "subqueries": subqueries,
            "rails_patterns": rails_patterns,
            "complexity": self._assess_complexity(sql_upper)
        }

    def _analyze_query_intent(self, sql_clean: str, sql_upper: str) -> Dict[str, Any]:
        """Determine the semantic intent of the SQL query."""
        intent = {
            "type": "unknown",
            "purpose": "data_retrieval",
            "characteristics": []
        }

        # Existence checks - multiple patterns
        if (re.search(r'SELECT\s+1\s+AS\s+one.*LIMIT\s+1', sql_upper) or
            re.search(r'SELECT\s+1\s+AS\s+one.*$', sql_upper) or
            re.search(r'SELECT\s+1\s+FROM.*LIMIT\s+1', sql_upper)):
            intent["type"] = "existence_check"
            intent["purpose"] = "validation"
            intent["characteristics"].append("boolean_result")

        # Count queries
        elif re.search(r'SELECT\s+COUNT\s*\(', sql_upper):
            intent["type"] = "count_query"
            intent["purpose"] = "aggregation"

        # Data insertion
        elif sql_upper.startswith('INSERT'):
            intent["type"] = "data_insertion"
            intent["purpose"] = "persistence"

        # Data updates
        elif sql_upper.startswith('UPDATE'):
            intent["type"] = "data_update"
            intent["purpose"] = "modification"

        # Transaction markers
        elif sql_upper in ('BEGIN', 'COMMIT', 'ROLLBACK'):
            intent["type"] = "transaction_control"
            intent["purpose"] = "data_integrity"

        # Complex selections
        else:
            intent["type"] = "data_selection"
            if 'ORDER BY' in sql_upper:
                intent["characteristics"].append("sorted")
            if 'LIMIT' in sql_upper:
                intent["characteristics"].append("limited")
            if 'JOIN' in sql_upper:
                intent["characteristics"].append("multi_table")

        return intent

    def _extract_tables(self, sql_upper: str) -> List[str]:
        """Extract all table names from the query."""
        tables = []

        # FROM clauses
        from_matches = re.findall(r'FROM\s+["`]?(\w+)["`]?', sql_upper)
        tables.extend([t.lower() for t in from_matches])

        # INSERT INTO
        insert_matches = re.findall(r'INSERT\s+INTO\s+["`]?(\w+)["`]?', sql_upper)
        tables.extend([t.lower() for t in insert_matches])

        # UPDATE
        update_matches = re.findall(r'UPDATE\s+["`]?(\w+)["`]?', sql_upper)
        tables.extend([t.lower() for t in update_matches])

        # JOIN clauses
        join_matches = re.findall(r'JOIN\s+["`]?(\w+)["`]?', sql_upper)
        tables.extend([t.lower() for t in join_matches])

        return list(dict.fromkeys(tables))  # Remove duplicates, preserve order

    def _extract_select_columns(self, sql_upper: str) -> List[str]:
        """Extract column information from SELECT clause."""
        select_match = re.search(r'SELECT\s+(.*?)\s+FROM', sql_upper, re.DOTALL)
        if not select_match:
            return []

        select_part = select_match.group(1).strip()

        # Handle special cases
        if re.search(r'1\s+AS\s+one', select_part):
            return ["existence_check"]
        if '*' in select_part:
            return ["all_columns"]
        if 'COUNT(' in select_part:
            return ["count_aggregate"]

        # Extract actual column names
        columns = []
        col_matches = re.findall(r'["`]?(\w+)["`]?(?:\s+AS\s+\w+)?', select_part)
        return [col.lower() for col in col_matches if col.lower() not in ('as', 'distinct')]

    def _extract_where_conditions(self, sql_upper: str, sql_clean: str) -> Dict[str, Any]:
        """Extract and analyze WHERE clause conditions."""
        where_match = re.search(r'WHERE\s+(.*?)(?:\s+ORDER|\s+GROUP|\s+LIMIT|$)', sql_upper, re.DOTALL)
        if not where_match:
            return {"has_where": False}

        where_clause = where_match.group(1).strip()

        return {
            "has_where": True,
            "raw_clause": where_clause,
            "columns": self._extract_where_columns(where_clause),
            "has_parameters": '$' in sql_clean or '?' in sql_clean,
            "has_subqueries": 'SELECT' in where_clause,
            "operators": self._extract_operators(where_clause),
            "is_complex": len(re.findall(r'\b(AND|OR)\b', where_clause)) > 1,
            "conditions": self._parse_where_conditions(where_clause)
        }

    def _extract_where_columns(self, where_clause: str) -> List[str]:
        """Extract column names from WHERE conditions."""
        # Match patterns like "table"."column" or table.column or just column before operators
        # Handle quoted identifiers properly
        col_matches = re.findall(r'["`]?(?:\w+["`]?\s*\.\s*["`]?)?([a-zA-Z_]\w*)["`]?\s*[=<>!]', where_clause)
        return [col.lower() for col in col_matches if col.lower() not in ('and', 'or')]

    def _extract_order_columns(self, sql_upper: str) -> List[Tuple[str, str]]:
        """Extract ORDER BY columns and direction."""
        order_match = re.search(r'ORDER\s+BY\s+(.*?)(?:\s+LIMIT|\s+OFFSET|$)', sql_upper)
        if not order_match:
            return []

        order_clause = order_match.group(1).strip()
        columns = []

        # Parse "column ASC/DESC" patterns, handling multiple columns
        for part in order_clause.split(','):
            part = part.strip()
            # Handle "table"."column" ASC/DESC or just "column" ASC/DESC
            col_match = re.match(r'["`]?(?:\w+["`]?\s*\.\s*["`]?)?([a-zA-Z_]\w+)["`]?\s*(ASC|DESC)?', part, re.I)
            if col_match:
                column = col_match.group(1).lower()
                direction = (col_match.group(2) or 'ASC').upper()
                columns.append((column, direction))

        return columns

    def _parse_where_conditions(self, where_clause: str) -> List[Dict[str, str]]:
        """Parse individual WHERE conditions."""
        conditions = []

        # Split by AND/OR but keep track of what we split by
        parts = re.split(r'\s+(AND|OR)\s+', where_clause, flags=re.IGNORECASE)

        for i in range(0, len(parts), 2):  # Skip the AND/OR separators
            condition_text = parts[i].strip()

            # Parse individual condition like "table"."column" = $1
            condition_match = re.match(
                r'["`]?(?:(\w+)["`]?\s*\.\s*)?["`]?(\w+)["`]?\s*([=<>!]+|LIKE|IN)\s*(.+)',
                condition_text,
                re.IGNORECASE
            )

            if condition_match:
                table, column, operator, value = condition_match.groups()
                conditions.append({
                    "table": table.lower() if table else None,
                    "column": column.lower(),
                    "operator": operator.upper(),
                    "value": value.strip(),
                    "raw": condition_text
                })

        return conditions

    def _extract_operators(self, where_clause: str) -> List[str]:
        """Extract comparison operators from WHERE clause."""
        return re.findall(r'(=|!=|<>|<=|>=|<|>|LIKE|IN|NOT IN|IS NULL|IS NOT NULL)', where_clause)

    def _extract_joins(self, sql_upper: str) -> List[Dict[str, str]]:
        """Extract JOIN information."""
        joins = []
        join_pattern = r'(LEFT\s+JOIN|RIGHT\s+JOIN|INNER\s+JOIN|JOIN)\s+(["`]?\w+["`]?)\s+ON\s+(.*?)(?:\s+(?:LEFT|RIGHT|INNER|JOIN|WHERE|ORDER|GROUP|LIMIT)|$)'

        for match in re.finditer(join_pattern, sql_upper, re.DOTALL):
            joins.append({
                "type": match.group(1).strip(),
                "table": match.group(2).strip().replace('`', '').replace('"', '').lower(),
                "condition": match.group(3).strip()
            })

        return joins

    def _detect_subqueries(self, sql_clean: str) -> List[str]:
        """Detect subqueries in the SQL."""
        # Simple subquery detection
        subquery_matches = re.findall(r'\(\s*(SELECT\s+.*?)\s*\)', sql_clean, re.IGNORECASE | re.DOTALL)
        return subquery_matches

    def _infer_rails_patterns(self, intent: Dict, tables: List[str], where_info: Dict, columns: List[str], sql_upper: str) -> List[str]:
        """Infer likely Rails/ActiveRecord patterns based on SQL analysis."""
        patterns = []

        if not tables:
            return patterns

        main_table = tables[0]
        model = self._table_to_model(main_table)

        # Existence checks with detailed condition analysis
        if intent["type"] == "existence_check":
            if where_info.get("conditions"):
                for condition in where_info["conditions"]:
                    col = condition["column"]
                    op = condition["operator"]

                    # Direct model existence check
                    if op == "=":
                        patterns.extend([
                            f"{model}.exists?({col}: value)",
                            f"{model}.where({col}: value).exists?",
                            f"{model}.find_by({col}: value).present?"
                        ])

                        # Association patterns for foreign keys
                        if col.endswith("_id"):
                            assoc_name = col[:-3]  # Remove "_id"
                            patterns.extend([
                                f"@{assoc_name}.{main_table}.exists?",
                                f"current_{assoc_name}.{main_table}.any?",
                                f"association.{main_table}.exists?"
                            ])

                    elif op in ["IN", "NOT IN"]:
                        patterns.extend([
                            f"{model}.exists?({col}: [values])",
                            f"{model}.where({col}: array).exists?"
                        ])

                    # Validation patterns
                    if op == "=" and col in ["id", "email", "username", "slug"]:
                        patterns.extend([
                            f"validates :field, uniqueness: true  # triggers {model}.exists?({col}: ...)",
                            f"validate :unique_{col}  # custom validation using exists?"
                        ])

            else:
                patterns.extend([
                    f"{model}.exists?",
                    f"{model}.any?",
                    f"@{main_table}.present?"
                ])

        # Count queries
        elif intent["type"] == "count_query":
            patterns.extend([
                f"{model}.count",
                f"{model}.where(...).count",
                f"association.count",
                f"association.size"  # Can trigger COUNT
            ])

        # Data insertion patterns
        elif intent["type"] == "data_insertion":
            patterns.extend([
                f"{model}.create(...)",
                f"{model}.new(...).save",
                f"build_{main_table[:-1]}(...)"  # Remove 's' for singular
            ])

        # Data update patterns
        elif intent["type"] == "data_update":
            patterns.extend([
                f"{model}.update(...)",
                f"@{main_table[:-1]}.save",  # Instance save
                f"{model}.update_all(...)"
            ])

        # Data selection with specific patterns
        elif intent["type"] == "data_selection":
            if "all_columns" in columns:
                if where_info.get("has_where"):
                    patterns.extend([
                        f"{model}.where({self._build_where_hash(where_info)})",
                        f"{model}.find_by({self._build_where_hash(where_info)})",
                        f"association.where(...)"
                    ])
                else:
                    patterns.extend([f"{model}.all", f"association.all"])

            if "limited" in intent.get("characteristics", []):
                patterns.extend([f"{model}.limit(...)", f"{model}.first", f"{model}.last"])

            if "sorted" in intent.get("characteristics", []):
                # Extract actual ORDER BY columns from the SQL
                order_columns = self._extract_order_columns(sql_upper)
                if order_columns:
                    for col, direction in order_columns:
                        # Generate specific patterns for the actual column
                        patterns.extend([
                            f"{model}.order(:{col})",
                            f"{model}.order('{col}')",
                            f'{model}.order("{col}")',
                            f"{model}.order({col}: :asc)" if direction == "ASC" else f"{model}.order({col}: :desc)",
                            f"{model}.all.order(:{col})",
                            f"@{main_table[:-1]}.order(:{col})"  # Instance variable pattern
                        ])
                else:
                    # Fallback to generic pattern if ORDER BY parsing fails
                    patterns.append(f"{model}.order(...)")

        return patterns

    def _build_where_hash(self, where_info: Dict) -> str:
        """Generate likely ActiveRecord where hash syntax from parsed conditions."""
        if not where_info.get("conditions"):
            return "..."

        conditions = where_info["conditions"]
        if len(conditions) == 1:
            condition = conditions[0]
            col = condition["column"]
            op = condition["operator"]

            if op == "=":
                return f"{col}: value"
            elif op in ["IN", "NOT IN"]:
                return f"{col}: [values]"
            elif op in ["LIKE"]:
                return f"{col}: '%pattern%'"
            else:
                return f'"{col} {op} ?"'
        else:
            # Multiple conditions
            parts = []
            for condition in conditions[:2]:  # Limit to 2 for readability
                col = condition["column"]
                parts.append(f"{col}: ?")
            return "{" + ", ".join(parts) + "}"

    def _assess_complexity(self, sql_upper: str) -> str:
        """Assess the complexity level of the SQL query."""
        complexity_score = 0

        if 'JOIN' in sql_upper:
            complexity_score += 2
        if 'SUBQUERY' in sql_upper or sql_upper.count('SELECT') > 1:
            complexity_score += 3
        if len(re.findall(r'\b(AND|OR)\b', sql_upper)) > 2:
            complexity_score += 2
        if any(word in sql_upper for word in ['GROUP BY', 'HAVING', 'UNION', 'WITH']):
            complexity_score += 2

        if complexity_score >= 5:
            return "high"
        elif complexity_score >= 2:
            return "medium"
        else:
            return "low"

    def _create_fingerprint(self, sql_info: Dict[str, Any]) -> str:
        """Create a normalized fingerprint of the SQL query."""
        intent = sql_info.get("intent", {})
        tables = sql_info.get("tables", [])
        columns = sql_info.get("columns", [])
        where_info = sql_info.get("where_info", {})

        # Handle existence checks specifically
        if intent.get("type") == "existence_check":
            table = tables[0] if tables else "table"
            base = f"SELECT 1 AS one FROM {table}"

            if where_info.get("conditions"):
                where_parts = []
                for condition in where_info["conditions"]:
                    col = condition["column"]
                    op = condition["operator"]
                    where_parts.append(f"{col} {op} ?")
                base += f" WHERE {' AND '.join(where_parts)}"

            # Add LIMIT for existence checks
            base += " LIMIT 1"
            return base

        # Handle other query types
        parts = []
        table = tables[0] if tables else "table"

        # SELECT part
        if "existence_check" in columns:
            parts.append(f"SELECT 1 AS one FROM {table}")
        elif "all_columns" in columns:
            parts.append(f"SELECT {table}.* FROM {table}")
        elif "count_aggregate" in columns:
            parts.append(f"SELECT COUNT(*) FROM {table}")
        elif columns:
            parts.append(f"SELECT {', '.join(columns)} FROM {table}")
        else:
            parts.append(f"SELECT * FROM {table}")

        # WHERE part
        if where_info.get("conditions"):
            where_parts = []
            for condition in where_info["conditions"]:
                col = condition["column"]
                op = condition["operator"]
                where_parts.append(f"{col} {op} ?")
            parts.append(f"WHERE {' AND '.join(where_parts)}")

        # LIMIT part
        if intent.get("type") == "existence_check":
            parts.append("LIMIT 1")

        return " ".join(parts)

    async def _find_definition_sites_semantic(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Intelligently search for Rails code using semantic analysis and adaptive strategies."""
        if not analysis.primary_model or not self.project_root:
            return []

        # Use multiple adaptive search strategies
        strategies = [
            self._strategy_direct_patterns,
            self._strategy_intent_based,
            self._strategy_association_based,
            self._strategy_validation_based,
            self._strategy_callback_based
        ]

        all_matches = []
        for strategy in strategies:
            matches = await strategy(analysis)
            all_matches.extend(matches)

        return all_matches

    async def _strategy_direct_patterns(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for direct Rails patterns inferred from the query."""
        matches = []

        for pattern in analysis.rails_patterns:
            # Extract searchable terms from pattern
            if ".exists?" in pattern:
                found = await self._search_pattern(r"\.exists\?\b", "rb")
                for result in found:
                    if analysis.primary_model.lower() in result["content"].lower():
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["direct pattern match", f"matches {pattern}"],
                            confidence="high (direct match)",
                            match_type="definition"
                        ))

            elif ".count" in pattern:
                found = await self._search_pattern(r"\.count\b", "rb")
                for result in found:
                    if analysis.primary_model.lower() in result["content"].lower():
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["count pattern match", f"matches {pattern}"],
                            confidence="high (direct match)",
                            match_type="definition"
                        ))

            elif ".where" in pattern:
                model_pattern = rf"{re.escape(analysis.primary_model)}\.where\b"
                found = await self._search_pattern(model_pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["where clause match", f"model: {analysis.primary_model}"],
                        confidence="high (model match)",
                        match_type="definition"
                    ))

            elif ".order" in pattern:
                # Extract the column name from pattern like "Product.order(:title)"
                col_match = re.search(r'\.order\([:\'"]*([a-zA-Z_]\w*)', pattern)
                if col_match:
                    col = col_match.group(1)
                    # Search for specific order patterns with the column
                    specific_patterns = [
                        rf'\.order\([:\'"]*{re.escape(col)}[:\'"]*\)',  # .order(:col) or .order('col')
                        rf'\.order\(\s*{re.escape(col)}\s*:\s*:asc\)',  # .order(col: :asc)
                        rf'\.order\(\s*{re.escape(col)}\s*:\s*:desc\)'  # .order(col: :desc)
                    ]
                    for search_pattern in specific_patterns:
                        found = await self._search_pattern(search_pattern, "rb")
                        for result in found[:3]:  # Limit per pattern
                            if analysis.primary_model.lower() in result["content"].lower():
                                matches.append(SQLMatch(
                                    path=result["file"],
                                    line=result["line"],
                                    snippet=result["content"],
                                    why=["order pattern match", f"column: {col}", f"matches {pattern}"],
                                    confidence="high (direct order match)",
                                    match_type="definition"
                                ))
                else:
                    # Generic .order search if we can't extract column
                    found = await self._search_pattern(r"\.order\b", "rb")
                    for result in found[:5]:
                        if analysis.primary_model.lower() in result["content"].lower():
                            matches.append(SQLMatch(
                                path=result["file"],
                                line=result["line"],
                                snippet=result["content"],
                                why=["generic order match", f"model: {analysis.primary_model}"],
                                confidence="medium (generic order)",
                                match_type="definition"
                            ))

        return matches[:10]  # Limit direct matches

    async def _strategy_intent_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search based on query semantic intent."""
        matches = []

        if analysis.intent == QueryIntent.EXISTENCE_CHECK:
            # Search for existence patterns
            patterns = [r"\.exists\?\b", r"\.any\?\b", r"\.present\?\b", r"\.empty\?\b"]
            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found[:3]:  # Limit per pattern
                    if any(table.rails_model.lower() in result["content"].lower()
                          for table in analysis.tables):
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["existence check pattern", "boolean validation"],
                            confidence="high (intent match)",
                            match_type="definition"
                        ))

        elif analysis.intent == QueryIntent.COUNT_AGGREGATE:
            patterns = [r"\.count\b", r"\.size\b", r"\.length\b"]
            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found[:3]:
                    if any(table.rails_model.lower() in result["content"].lower()
                          for table in analysis.tables):
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["count/size operation", "aggregation pattern"],
                            confidence="high (aggregation)",
                            match_type="definition"
                        ))

        return matches

    async def _strategy_association_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for association-based patterns."""
        matches = []

        for condition in analysis.where_conditions:
            if condition.column.is_foreign_key:
                assoc_name = condition.column.association_name

                # Search for association usage
                patterns = [
                    rf"\.{assoc_name}\b",
                    rf"\.{assoc_name}s\b",
                    rf"@{assoc_name}\.",
                    rf"current_{assoc_name}\b"
                ]

                for pattern in patterns:
                    found = await self._search_pattern(pattern, "rb")
                    for result in found[:2]:  # Limit association matches
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["association usage", f"foreign key: {condition.column.name}"],
                            confidence="medium (association)",
                            match_type="definition"
                        ))

        return matches

    async def _strategy_validation_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for validation patterns that might trigger existence checks."""
        matches = []

        if analysis.intent == QueryIntent.EXISTENCE_CHECK:
            validation_patterns = [
                r"validates.*uniqueness",
                r"validate\s+:\w+.*unique",
                rf"validates.*{analysis.primary_model.lower()}",
                r"before_validation.*exists"
            ]

            for pattern in validation_patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found[:2]:  # Limit validation matches
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["validation pattern", "may trigger existence check"],
                        confidence="medium (validation)",
                        match_type="definition"
                    ))

        return matches

    async def _strategy_callback_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for callbacks that might indirectly trigger queries."""
        matches = []

        callback_patterns = [
            r"after_create\b",
            r"before_save\b",
            r"after_commit\b",
            r"after_update\b"
        ]

        for pattern in callback_patterns:
            found = await self._search_pattern(pattern, "rb")
            for result in found[:2]:  # Limit callback matches
                if any(table.rails_model.lower() in result["content"].lower()
                      for table in analysis.tables):
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["callback pattern", "indirect query trigger"],
                        confidence="low (callback)",
                        match_type="definition"
                    ))

        return matches

    async def _search_rails_pattern(self, pattern_desc: str, sql_info: Dict) -> List[SQLMatch]:
        """Search for specific Rails patterns."""
        matches = []

        # Extract searchable terms from pattern description
        if "exists?" in pattern_desc:
            # Search for .exists? usage
            found = await self._search_pattern(r"\.exists\?", "rb")
            for result in found:
                if any(model.lower() in result["content"].lower() for model in sql_info.get("models", [])):
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["existence check pattern", "matches .exists? usage"],
                        confidence="high (semantic match)",
                        match_type="definition"
                    ))

        elif "count" in pattern_desc:
            # Search for .count usage
            found = await self._search_pattern(r"\.count\b", "rb")
            for result in found:
                if any(model.lower() in result["content"].lower() for model in sql_info.get("models", [])):
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["count aggregation", "matches .count usage"],
                        confidence="high (semantic match)",
                        match_type="definition"
                    ))

        elif "where" in pattern_desc:
            # Search for .where usage with the model
            for model in sql_info.get("models", []):
                pattern = rf"{re.escape(model)}\.where"
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["where condition", f"{model} filtering"],
                        confidence="high (model match)",
                        match_type="definition"
                    ))

        return matches

    async def _search_existence_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for patterns that generate existence check queries."""
        matches = []

        for model in sql_info.get("models", []):
            # Pattern 1: Direct exists? calls
            patterns = [
                rf"{re.escape(model)}\.exists\?",
                rf"\.exists\?\s*$",  # End of line exists?
                rf"if\s+.*\.exists\?",  # Conditional exists?
                rf"unless\s+.*\.exists\?",  # Unless exists?
            ]

            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["existence check", "boolean validation"],
                        confidence="high (existence pattern)",
                        match_type="definition"
                    ))

            # Pattern 2: Validation methods that might use exists?
            validation_patterns = [
                rf"validates.*uniqueness",
                rf"validate\s+:.*{model.lower()}",
                rf"before_.*\s+.*{model.lower()}"
            ]

            for pattern in validation_patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["validation logic", "may trigger existence check"],
                        confidence="medium (validation)",
                        match_type="definition"
                    ))

        return matches

    async def _search_count_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for patterns that generate count queries."""
        matches = []

        for model in sql_info.get("models", []):
            patterns = [
                rf"{re.escape(model)}\.count",
                rf"\.count\s*$",
                rf"\.size\b",  # .size can trigger count
                rf"\.length\b"  # .length can trigger count
            ]

            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["count/size operation"],
                        confidence="high (aggregation)",
                        match_type="definition"
                    ))

        return matches

    async def _search_insertion_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for patterns that generate INSERT queries."""
        matches = []

        for model in sql_info.get("models", []):
            patterns = [
                rf"{re.escape(model)}\.create",
                rf"{re.escape(model)}\.new.*\.save",
                rf"\.create!",
                rf"build_.*{model.lower()}",
                rf"{model.lower()}\.build"
            ]

            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["record creation", "INSERT operation"],
                        confidence="high (creation pattern)",
                        match_type="definition"
                    ))

        return matches

    async def _search_update_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for patterns that generate UPDATE queries."""
        matches = []

        for model in sql_info.get("models", []):
            patterns = [
                rf"{re.escape(model)}\.update",
                rf"\.update!",
                rf"\.update_attribute",
                rf"\.save\b",
                rf"\.save!"
            ]

            for pattern in patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["record update", "UPDATE operation"],
                        confidence="high (update pattern)",
                        match_type="definition"
                    ))

        return matches

    async def _search_association_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for association-based patterns that might generate the query."""
        matches = []

        # Look for foreign key relationships in WHERE clauses
        where_info = sql_info.get("where_info", {})
        if where_info.get("columns"):
            for column in where_info["columns"]:
                if column.endswith("_id"):
                    # This might be a foreign key - search for association usage
                    base_name = column[:-3]  # Remove "_id"

                    patterns = [
                        rf"\.{base_name}\b",  # belongs_to association
                        rf"\.{base_name}s\b",  # has_many association
                        rf"through.*{base_name}",  # has_many through
                        rf"includes.*{base_name}"  # eager loading
                    ]

                    for pattern in patterns:
                        found = await self._search_pattern(pattern, "rb")
                        for result in found[:3]:  # Limit results
                            matches.append(SQLMatch(
                                path=result["file"],
                                line=result["line"],
                                snippet=result["content"],
                                why=["association access", f"foreign key: {column}"],
                                confidence="medium (association)",
                                match_type="definition"
                            ))

        return matches

    async def _search_callback_patterns(self, sql_info: Dict) -> List[SQLMatch]:
        """Search for callbacks that might trigger the query."""
        matches = []

        for model in sql_info.get("models", []):
            callback_patterns = [
                rf"after_create.*{model.lower()}",
                rf"before_save.*{model.lower()}",
                rf"after_commit",
                rf"after_update.*{model.lower()}",
                rf"validate.*{model.lower()}"
            ]

            for pattern in callback_patterns:
                found = await self._search_pattern(pattern, "rb")
                for result in found[:2]:  # Limit callback matches
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["callback execution", "indirect query trigger"],
                        confidence="low (callback)",
                        match_type="definition"
                    ))

        return matches

    async def _find_usage_sites(self, definition_matches: List[SQLMatch]) -> List[SQLMatch]:
        """Find where the defined queries are actually used/executed."""
        usage_matches = []

        # Look for instance variable usage in views
        for def_match in definition_matches:
            # Extract instance variable name from snippet like "@products = Product.order(:title)"
            ivar_match = re.search(r'(@\w+)\s*=', def_match.snippet)
            if ivar_match:
                ivar_name = ivar_match.group(1)

                # Search for usage in ERB files
                pattern = rf"{re.escape(ivar_name)}\.each\b"
                found = await self._search_pattern(pattern, "erb")
                for result in found:
                    usage_matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["enumerates the relation (executes SELECT)"],
                        confidence="medium (execution site)",
                        match_type="usage"
                    ))

                # Also search for direct usage
                pattern = rf"{re.escape(ivar_name)}\b"
                found = await self._search_pattern(pattern, "erb")
                for result in found[:3]:  # Limit to avoid noise
                    if "each" not in result["content"]:  # Avoid duplicates
                        usage_matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["references the query result"],
                            confidence="low (reference)",
                            match_type="usage"
                        ))

        return usage_matches

    async def _search_pattern(self, pattern: str, file_ext: str) -> List[Dict[str, Any]]:
        """Execute ripgrep search for a pattern."""
        if not self.project_root:
            self._debug_log("❌ No project root set")
            return []

        cmd = [
            "rg", "--line-number", "--with-filename", "-i",
            "--type-add", f"target:*.{file_ext}",
            "--type", "target",
            pattern,
            self.project_root
        ]

        self._debug_log("🔍 Executing ripgrep", {
            "pattern": pattern,
            "file_ext": file_ext,
            "command": " ".join(cmd)
        })

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            matches = []

            if result.returncode in (0, 1):
                for line in result.stdout.splitlines():
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path, line_num, content = parts
                        try:
                            matches.append({
                                "file": self._rel_path(file_path),
                                "line": int(line_num),
                                "content": content.strip()
                            })
                        except ValueError:
                            continue

            self._debug_log("📊 Ripgrep results", {
                "return_code": result.returncode,
                "matches_found": len(matches),
                "stderr": result.stderr[:200] if result.stderr else None
            })

            return matches
        except Exception as e:
            self._debug_log("❌ Ripgrep error", f"{type(e).__name__}: {e}")
            return []

    def _rank_matches(self, matches: List[SQLMatch], analysis: QueryAnalysis) -> List[SQLMatch]:
        """Rank matches by confidence and relevance, removing duplicates."""
        # Remove duplicates based on path and line
        seen = set()
        unique_matches = []

        for match in matches:
            key = (match.path, match.line)
            if key not in seen:
                seen.add(key)
                unique_matches.append(match)

        def confidence_score(match: SQLMatch) -> int:
            if "high" in match.confidence:
                return 3
            elif "medium" in match.confidence:
                return 2
            else:
                return 1

        def type_score(match: SQLMatch) -> int:
            return 2 if match.match_type == "definition" else 1

        return sorted(unique_matches, key=lambda m: (confidence_score(m), type_score(m)), reverse=True)

    def _generate_verify_command(self, sql_info: Dict[str, Any]) -> Optional[str]:
        """Generate Rails console command to verify the query."""
        models = sql_info.get("models", [])
        if not models:
            return None

        model = models[0]
        intent = sql_info.get("intent", {})
        where_info = sql_info.get("where_info", {})

        # Generate command based on query intent
        if intent.get("type") == "existence_check":
            if where_info.get("conditions"):
                condition = where_info["conditions"][0]
                col = condition["column"]
                if col.endswith("_id"):
                    return f"rails runner 'puts {model}.exists?({col}: 1)'"
                else:
                    return f"rails runner 'puts {model}.exists?({col}: \"test_value\")'"
            else:
                return f"rails runner 'puts {model}.exists?'"

        elif intent.get("type") == "count_query":
            return f"rails runner 'puts {model}.count'"

        elif intent.get("type") == "data_insertion":
            return f"rails runner 'puts {model}.new.save'"

        elif intent.get("type") == "data_update":
            return f"rails runner 'puts {model}.update_all(updated_at: Time.current)'"

        else:
            # Default data selection
            base_cmd = model

            if where_info.get("conditions"):
                condition = where_info["conditions"][0]
                col = condition["column"]
                base_cmd += f".where({col}: \"test_value\")"

            return f"rails runner 'puts {base_cmd}.to_sql'"

    def _table_to_model(self, table: str) -> str:
        """Convert table name to Rails model name."""
        # Basic singularization and capitalization
        table = table.lower()
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

        return "".join(word.capitalize() for word in singular.split("_"))

    def _rel_path(self, file_path: str) -> str:
        """Convert absolute path to relative path."""
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

    def _is_transaction_log(self, sql: str) -> bool:
        """Check if the input appears to be a transaction log with multiple queries."""
        lines = sql.strip().split('\n')

        # Look for timestamp patterns typical of MySQL general log
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+\d+\s+\w+'

        # Count lines that look like log entries
        log_lines = sum(1 for line in lines if re.match(timestamp_pattern, line.strip()))

        # If we have multiple timestamped entries, it's likely a transaction log
        if log_lines >= 3:
            return True

        # Also check for explicit transaction boundaries
        has_begin = any('BEGIN' in line.upper() for line in lines)
        has_commit = any('COMMIT' in line.upper() for line in lines)
        multiple_queries = len([line for line in lines if any(op in line.upper() for op in ['SELECT', 'INSERT', 'UPDATE', 'DELETE'])]) >= 3

        return has_begin and has_commit and multiple_queries

    def _count_queries_in_log(self, sql: str) -> int:
        """Count the number of SQL queries in a transaction log."""
        lines = sql.strip().split('\n')
        query_count = 0

        for line in lines:
            line_clean = line.strip()
            # Skip empty lines
            if not line_clean:
                continue

            # Look for SQL operations anywhere in the line (after timestamp)
            line_upper = line_clean.upper()
            if any(op in line_upper for op in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'BEGIN', 'COMMIT']):
                query_count += 1

        return query_count
