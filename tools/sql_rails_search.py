"""
Unified SQL-to-Rails Code Search Tool

Single tool exposed to LLM that intelligently routes SQL queries to appropriate
search strategies based on input type:

- Single SQL query → Progressive refinement search with domain rules
- Multiple queries → Batch search with shared patterns
- Transaction log → Transaction analyzer with progressive search

Uses generalizable search strategies - no hardcoded patterns.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path

from .base_tool import BaseTool
from .components.sql_log_classifier import SQLLogClassifier
from .components.sql_log_extractor import AdaptiveSQLExtractor, SQLType
from .semantic_sql_analyzer import SemanticSQLAnalyzer
from .components.code_search_engine import CodeSearchEngine
from .components.progressive_search_engine import ProgressiveSearchEngine
from .components.rails_search_rules import RailsSearchRuleSet


class SQLRailsSearch(BaseTool):
    """
    Unified SQL-to-Rails code search tool with intelligent routing.

    Automatically detects input type and uses appropriate search strategy.
    """

    def __init__(self, project_root: Optional[str] = None, debug: bool = False, spinner=None):
        super().__init__(project_root, debug, spinner)

        # Initialize components
        self.sql_analyzer = SemanticSQLAnalyzer()
        self.sql_classifier = SQLLogClassifier()
        self.sql_extractor = AdaptiveSQLExtractor()
        self.code_search_engine = CodeSearchEngine(
            project_root=self.project_root,
            debug_log=self._debug_log
        )
        self.progressive_search = ProgressiveSearchEngine(
            code_search_engine=self.code_search_engine,
            project_root=self.project_root or "",
            debug=debug
        )
        self.rule_set = RailsSearchRuleSet()

    @property
    def name(self) -> str:
        return "sql_rails_search"

    @property
    def description(self) -> str:
        return (
            "Search for Rails source code that generates SQL queries. "
            "Automatically detects whether input is a single query, multiple queries, "
            "or transaction log, and uses appropriate search strategy. "
            "Uses progressive refinement with domain-aware rules - works for ANY SQL query."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "SQL query or transaction log to trace"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of matches to return",
                    "default": 10
                },
                "include_explanation": {
                    "type": "boolean",
                    "description": "Include search strategy explanation in results",
                    "default": False
                }
            },
            "required": ["sql"]
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Execute unified SQL search with intelligent routing.

        Steps:
        1. Classify input (single query | multi-query | transaction)
        2. Route to appropriate strategy
        3. Return normalized results
        """
        self._debug_input(input_params)

        if not self.validate_input(input_params):
            return {"error": "Invalid input"}

        sql = input_params.get("sql", "").strip()
        max_results = int(input_params.get("max_results", 10))
        include_explanation = bool(input_params.get("include_explanation", False))

        if not sql:
            return {"error": "Empty SQL input"}

        # Step 1: Classify input type
        classification = self.sql_classifier.classify(sql)

        self._debug_log("🔍 SQL Classification", {
            "type": classification.input_type.value,
            "reason": classification.reason,
            "query_count": classification.query_count
        })

        # Step 2: Route to appropriate strategy
        if classification.is_transaction():
            result = self._handle_transaction(sql, max_results, include_explanation)
        elif classification.query_count > 1:
            result = self._handle_multi_query(sql, max_results, include_explanation)
        else:
            result = self._handle_single_query(sql, max_results, include_explanation)

        self._debug_output(result)
        return result

    def _handle_single_query(
        self,
        sql: str,
        max_results: int,
        include_explanation: bool
    ) -> Dict[str, Any]:
        """
        Handle single SQL query using progressive refinement search.

        Strategy:
        1. Parse SQL to extract patterns
        2. Rank patterns by distinctiveness
        3. Search progressively (rare → common)
        4. Validate completeness
        5. Return top matches
        """
        self._debug_log("📍 Strategy", "Single query - progressive refinement")

        # Extract SQL if needed (remove log metadata)
        extracted = self.sql_extractor.extract_all_sql(sql)
        if extracted and len(extracted) == 1:
            sql = extracted[0].sql

        # Analyze SQL semantically
        try:
            analysis = self.sql_analyzer.analyze(sql)
        except Exception as e:
            return {
                "error": f"SQL analysis failed: {str(e)}",
                "sql": sql
            }

        # Use progressive search with domain rules
        try:
            results = self.progressive_search.search_progressive(
                sql_analysis=analysis,
                max_results=max_results
            )
        except Exception as e:
            return {
                "error": f"Progressive search failed: {str(e)}",
                "sql": sql
            }

        # Build response
        response = {
            "search_type": "single_query",
            "query_analysis": {
                "intent": analysis.intent.value,
                "table": analysis.primary_table.name if analysis.primary_table else None,
                "complexity": analysis.complexity
            },
            "matches": [
                {
                    "file": r.file,
                    "line": r.line,
                    "snippet": r.content[:100],  # Truncate for brevity
                    "confidence": f"{r.confidence:.2f}",
                    "why": r.why
                }
                for r in results
            ],
            "match_count": len(results)
        }

        if include_explanation:
            response["search_strategy"] = self._explain_single_query_strategy(analysis)

        return response

    def _handle_multi_query(
        self,
        sql: str,
        max_results: int,
        include_explanation: bool
    ) -> Dict[str, Any]:
        """
        Handle multiple SQL queries (not a full transaction).

        Strategy:
        1. Extract individual queries
        2. Find shared patterns (common table, operations)
        3. Search for code that generates these patterns
        4. Return matches sorted by relevance
        """
        self._debug_log("📍 Strategy", "Multi-query - shared pattern search")

        # Extract queries
        extracted = self.sql_extractor.extract_all_sql(sql)

        if not extracted:
            return {
                "error": "Could not extract queries from input",
                "sql": sql
            }

        # Analyze each query
        analyses = []
        for stmt in extracted:
            try:
                analysis = self.sql_analyzer.analyze(stmt.sql)
                analyses.append(analysis)
            except Exception:
                continue

        if not analyses:
            return {
                "error": "Could not analyze any queries",
                "query_count": len(extracted)
            }

        # Find shared patterns
        shared_tables = self._find_shared_tables(analyses)
        shared_operations = self._find_shared_operations(analyses)

        # Search for code that works with these shared patterns
        results = []
        if shared_tables:
            for table in shared_tables:
                # Search for code that operates on this table
                table_results = self.code_search_engine.search(table, "rb")
                results.extend(table_results[:5])  # Top 5 per table

        # Deduplicate
        seen = set()
        unique_results = []
        for r in results:
            key = f"{r.get('file', '')}:{r.get('line', 0)}"
            if key not in seen:
                seen.add(key)
                unique_results.append(r)

        response = {
            "search_type": "multi_query",
            "query_count": len(extracted),
            "shared_patterns": {
                "tables": list(shared_tables),
                "operations": list(shared_operations)
            },
            "matches": [
                {
                    "file": r.get("file", ""),
                    "line": r.get("line", 0),
                    "snippet": r.get("content", "")[:100]
                }
                for r in unique_results[:max_results]
            ],
            "match_count": len(unique_results)
        }

        if include_explanation:
            response["search_strategy"] = "Search for shared patterns across multiple queries"

        return response

    def _handle_transaction(
        self,
        sql: str,
        max_results: int,
        include_explanation: bool
    ) -> Dict[str, Any]:
        """
        Handle transaction log using transaction analyzer.

        Delegates to existing transaction_analyzer tool but uses
        progressive search infrastructure internally.
        """
        self._debug_log("📍 Strategy", "Transaction - delegate to transaction_analyzer")

        # Import transaction analyzer
        from .transaction_analyzer import TransactionAnalyzer

        # Create transaction analyzer (shares search infrastructure)
        transaction_analyzer = TransactionAnalyzer(
            project_root=self.project_root,
            debug=self.debug_enabled,
            spinner=None
        )

        # Execute transaction analysis
        result = transaction_analyzer.execute({
            "transaction_log": sql,
            "find_source_code": True,
            "max_patterns": max_results
        })

        # Add search type metadata
        result["search_type"] = "transaction"

        if include_explanation:
            result["search_strategy"] = (
                "Transaction flow analysis with progressive search for wrapper code"
            )

        return result

    def _find_shared_tables(self, analyses: List[Any]) -> set:
        """Find tables that appear in multiple queries."""
        table_counts = {}
        for analysis in analyses:
            if analysis.primary_table:
                table_name = analysis.primary_table.name
                table_counts[table_name] = table_counts.get(table_name, 0) + 1

        # Tables that appear in 2+ queries are considered shared
        return {table for table, count in table_counts.items() if count >= 2}

    def _find_shared_operations(self, analyses: List[Any]) -> set:
        """Find operations that appear in multiple queries."""
        operation_counts = {}
        for analysis in analyses:
            intent = analysis.intent.value
            operation_counts[intent] = operation_counts.get(intent, 0) + 1

        return {op for op, count in operation_counts.items() if count >= 2}

    def _explain_single_query_strategy(self, analysis: Any) -> Dict[str, Any]:
        """Explain the search strategy used for a single query."""
        # Get applicable rules
        applicable_rules = self.rule_set.get_applicable_rules(analysis)

        return {
            "approach": "Progressive refinement with domain-aware rules",
            "applicable_rules": [type(r).__name__ for r in applicable_rules],
            "steps": [
                "1. Extract distinctive patterns from SQL (LIMIT, scopes, columns)",
                "2. Rank patterns by distinctiveness (rare → common)",
                "3. Search for most distinctive pattern first",
                "4. Refine results by filtering for additional patterns",
                "5. Validate completeness (all SQL clauses accounted for)",
                "6. Return top matches with confidence scores"
            ],
            "domain_knowledge": {
                "WHERE clauses": "Model scopes and constants",
                "LIMIT/OFFSET": "Pagination contexts (mailers, jobs, controllers)",
                "ORDER BY": "Sorting contexts",
                "Foreign keys": "Association wrappers"
            }
        }
