"""
SQL Transaction Analyzer Tool

Analyzes complete SQL transaction logs to understand the flow of operations
and map them to Rails/ActiveRecord patterns and source code locations.
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .base_tool import BaseTool
from .sql_rails_search import SQLRailsSearchTool
from .enhanced_sql_rails_search import EnhancedSQLRailsSearch
from .model_analyzer import ModelAnalyzer


@dataclass
class SQLQuery:
    """Represents a single SQL query within a transaction."""
    timestamp: str
    connection_id: str
    query_type: str  # Query, Prepare, Execute, etc.
    sql: str
    operation: str  # INSERT, SELECT, UPDATE, DELETE, BEGIN, COMMIT
    table: Optional[str] = None
    references: List[str] = None  # Referenced IDs/values from other queries

    def __post_init__(self):
        if self.references is None:
            self.references = []


@dataclass
class TransactionFlow:
    """Represents the flow and relationships in a transaction."""
    queries: List[SQLQuery]
    trigger_chain: List[Tuple[str, str]]  # (trigger_query, triggered_query) pairs
    data_flow: Dict[str, List[str]]  # table -> referenced values
    rails_patterns: List[Dict[str, Any]]


class TransactionAnalyzer(BaseTool):
    """Analyzes complete SQL transaction logs for Rails code patterns."""

    @property
    def name(self) -> str:
        return "transaction_analyzer"

    @property
    def description(self) -> str:
        return (
            "Analyze complete SQL transaction logs to identify Rails patterns, "
            "callback chains, and source code locations for all operations"
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "transaction_log": {
                    "type": "string",
                    "description": "Complete SQL transaction log with timestamps"
                },
                "find_source_code": {
                    "type": "boolean",
                    "description": "Search for source code that generates these queries",
                    "default": True
                },
                "max_patterns": {
                    "type": "integer",
                    "description": "Maximum number of Rails patterns to search for",
                    "default": 10
                }
            },
            "required": ["transaction_log"]
        }

    async def execute(self, input_params: Dict[str, Any]) -> Any:
        if not self.validate_input(input_params):
            return {"error": "Invalid input"}

        transaction_log = input_params.get("transaction_log", "").strip()
        find_source = bool(input_params.get("find_source_code", True))
        max_patterns = int(input_params.get("max_patterns", 10))

        if not transaction_log:
            return {"error": "Empty transaction log"}

        try:
            # Parse the transaction log
            flow = self._parse_transaction_log(transaction_log)

            # Analyze Rails patterns
            self._analyze_transaction_patterns(flow)

            # Analyze models in the transaction
            model_analysis = {}
            if self.project_root:
                model_analysis = await self._analyze_models_in_transaction(flow)

            # Find source code if requested
            source_findings = []
            if find_source and self.project_root:
                source_findings = await self._find_source_code(flow, max_patterns)

            # Generate transaction summary
            summary = self._generate_transaction_summary(flow, source_findings, model_analysis)

            return {
                "transaction_summary": summary,
                "query_count": len(flow.queries),
                "tables_affected": list(set(q.table for q in flow.queries if q.table)),
                "operation_types": list(set(q.operation for q in flow.queries if q.operation)),
                "transaction_patterns": flow.rails_patterns,
                "trigger_chains": flow.trigger_chain,
                "data_flow": flow.data_flow,
                "model_analysis": model_analysis,
                "source_code_findings": source_findings,
                "visualization": self._create_flow_visualization(flow)
            }

        except Exception as e:
            return {"error": f"Transaction analysis failed: {str(e)}"}

    def _parse_transaction_log(self, log: str) -> TransactionFlow:
        """Parse MySQL general log format into structured queries."""
        lines = log.strip().split('\n')
        queries = []
        current_query = None

        # MySQL general log pattern: YYYY-MM-DDTHH:MM:SS.microsZ connection_id Query SQL
        log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(\d+)\s+(\w+)\s+(.+)$')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = log_pattern.match(line)
            if match:
                timestamp, conn_id, query_type, sql = match.groups()

                # Determine operation type
                operation = self._extract_operation(sql)
                table = self._extract_table(sql, operation)

                query = SQLQuery(
                    timestamp=timestamp,
                    connection_id=conn_id,
                    query_type=query_type,
                    sql=sql,
                    operation=operation,
                    table=table
                )

                queries.append(query)
            elif current_query:
                # Multi-line query continuation
                current_query.sql += " " + line

        # Analyze data flow and relationships
        flow = TransactionFlow(
            queries=queries,
            trigger_chain=[],
            data_flow={},
            rails_patterns=[]
        )

        self._analyze_data_flow(flow)
        self._identify_trigger_chains(flow)

        return flow

    def _extract_operation(self, sql: str) -> str:
        """Extract the main SQL operation type."""
        sql_upper = sql.upper().strip()

        if sql_upper.startswith('SELECT'):
            return 'SELECT'
        elif sql_upper.startswith('INSERT'):
            return 'INSERT'
        elif sql_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif sql_upper.startswith('DELETE'):
            return 'DELETE'
        elif sql_upper.startswith('BEGIN'):
            return 'BEGIN'
        elif sql_upper.startswith('COMMIT'):
            return 'COMMIT'
        elif sql_upper.startswith('ROLLBACK'):
            return 'ROLLBACK'
        else:
            return 'OTHER'

    def _extract_table(self, sql: str, operation: str) -> Optional[str]:
        """Extract the primary table name from SQL."""
        sql_clean = re.sub(r'`', '', sql)  # Remove backticks

        if operation == 'INSERT':
            match = re.search(r'INSERT\s+INTO\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'SELECT':
            match = re.search(r'FROM\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'UPDATE':
            match = re.search(r'UPDATE\s+(\w+)', sql_clean, re.IGNORECASE)
        elif operation == 'DELETE':
            match = re.search(r'FROM\s+(\w+)', sql_clean, re.IGNORECASE)
        else:
            return None

        return match.group(1) if match else None

    def _analyze_data_flow(self, flow: TransactionFlow) -> None:
        """Analyze how data flows between queries via values and references."""
        value_tracker = {}  # stores all values and where they appear

        for i, query in enumerate(flow.queries):
            if not query.table:
                continue

            # Extract all numeric values from the query (potential IDs)
            numeric_values = re.findall(r'\b\d{4,}\b', query.sql)  # Numbers with 4+ digits (likely IDs)

            # Extract string values that might be keys
            string_values = re.findall(r"'([a-zA-Z_]{3,})'", query.sql)  # Strings like table names, keys

            # Track values in this query
            all_values = numeric_values + string_values

            for value in all_values:
                if value not in value_tracker:
                    value_tracker[value] = {
                        'first_seen': i,
                        'first_table': query.table,
                        'queries': []
                    }
                value_tracker[value]['queries'].append({
                    'index': i,
                    'table': query.table,
                    'operation': query.operation,
                    'timestamp': query.timestamp
                })

        # Now identify data flow patterns
        for value, info in value_tracker.items():
            if len(info['queries']) > 1:  # Value appears in multiple queries
                # This suggests data flow
                for query_info in info['queries'][1:]:  # Skip first occurrence
                    query_idx = query_info['index']
                    query = flow.queries[query_idx]
                    query.references.append(f"{info['first_table']}#{value}")

        # Store simplified data flow info
        flow.data_flow = {
            table: [v for v, info in value_tracker.items() if info['first_table'] == table and len(info['queries']) > 1]
            for table in set(q.table for q in flow.queries if q.table)
        }

    def _identify_trigger_chains(self, flow: TransactionFlow) -> None:
        """Identify which queries likely triggered other queries."""
        trigger_pairs = []

        for i, query in enumerate(flow.queries):
            if query.operation == 'INSERT':
                # Look for subsequent queries that reference this insert
                for j in range(i + 1, len(flow.queries)):
                    next_query = flow.queries[j]

                    # Check if next query references data from this insert
                    if (next_query.references and
                        any(ref.startswith(query.table or '') for ref in next_query.references)):
                        trigger_pairs.append((f"{query.table}#{i}", f"{next_query.table}#{j}"))

                    # Special patterns for Rails callbacks
                    if (query.table == 'page_views' and
                        next_query.table == 'audit_logs'):
                        trigger_pairs.append(('page_views_insert', 'audit_log_callback'))
                    elif (query.table == 'audit_logs' and
                          next_query.table in ['member_actions_feed_items', 'content_usage_feed_items']):
                        trigger_pairs.append(('audit_log_insert', 'feed_item_callback'))

        flow.trigger_chain = trigger_pairs

    def _analyze_transaction_patterns(self, flow: TransactionFlow) -> None:
        """Analyze transaction patterns using generic structural analysis."""
        patterns = []

        # Pattern 1: CASCADE INSERTS - One INSERT triggers others
        insert_queries = [q for q in flow.queries if q.operation == 'INSERT']
        if len(insert_queries) > 1:
            # Check for rapid succession (within 50ms)
            for i in range(len(insert_queries) - 1):
                time_diff = self._get_time_diff_ms(insert_queries[i].timestamp, insert_queries[i+1].timestamp)
                if time_diff < 50:
                    patterns.append({
                        "pattern_type": "cascade_insert",
                        "description": f"INSERT into {insert_queries[i].table} triggers INSERT into {insert_queries[i+1].table}",
                        "sequence": [insert_queries[i].table, insert_queries[i+1].table],
                        "time_diff_ms": time_diff,
                        "likely_cause": "ActiveRecord callback (after_create, after_save) or observer"
                    })

        # Pattern 2: READ-MODIFY-WRITE - SELECT followed by UPDATE on same table
        for i in range(len(flow.queries) - 1):
            current = flow.queries[i]
            next_query = flow.queries[i + 1]

            if (current.operation == 'SELECT' and
                next_query.operation == 'UPDATE' and
                current.table == next_query.table):

                time_diff = self._get_time_diff_ms(current.timestamp, next_query.timestamp)
                patterns.append({
                    "pattern_type": "read_modify_write",
                    "description": f"SELECT from {current.table} immediately followed by UPDATE",
                    "table": current.table,
                    "time_diff_ms": time_diff,
                    "likely_cause": "Counter cache, optimistic locking, or calculated field update"
                })

        # Pattern 3: BULK OPERATIONS - Multiple similar operations
        operation_groups = {}
        for query in flow.queries:
            key = f"{query.operation}_{query.table}"
            if key not in operation_groups:
                operation_groups[key] = []
            operation_groups[key].append(query)

        for key, queries in operation_groups.items():
            if len(queries) > 2:
                patterns.append({
                    "pattern_type": "bulk_operation",
                    "description": f"Multiple {queries[0].operation} operations on {queries[0].table}",
                    "count": len(queries),
                    "table": queries[0].table,
                    "likely_cause": "Batch processing, analytics updates, or data migration"
                })

        # Pattern 4: DATA FLOW CHAINS - Track value references
        for i, query in enumerate(flow.queries):
            if query.references:
                for ref in query.references:
                    ref_table = ref.split('#')[0]
                    patterns.append({
                        "pattern_type": "data_flow",
                        "description": f"Value from {ref_table} used in {query.table} operation",
                        "from_table": ref_table,
                        "to_table": query.table,
                        "operation": query.operation,
                        "likely_cause": "Foreign key relationship or data dependency"
                    })

        # Pattern 5: CONTROLLER CONTEXT - Extract any controller/action information
        for query in flow.queries:
            controller_match = re.search(r"'controller'\s*[,=]\s*'([^']+)'", query.sql)
            action_match = re.search(r"'action'\s*[,=]\s*'([^']+)'", query.sql)

            if controller_match and action_match:
                patterns.append({
                    "pattern_type": "controller_context",
                    "description": f"Operation in context of {controller_match.group(1)}#{action_match.group(1)}",
                    "controller": controller_match.group(1),
                    "action": action_match.group(1),
                    "table": query.table,
                    "likely_source": f"{controller_match.group(1).title().replace('_', '')}Controller#{action_match.group(1)}"
                })

        flow.rails_patterns = patterns

    def _get_time_diff_ms(self, timestamp1: str, timestamp2: str) -> float:
        """Calculate time difference in milliseconds between two timestamps."""
        try:
            from datetime import datetime

            # Parse ISO format timestamps: 2025-08-19T08:21:23.381609Z
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            dt1 = datetime.strptime(timestamp1, fmt)
            dt2 = datetime.strptime(timestamp2, fmt)

            diff = (dt2 - dt1).total_seconds() * 1000
            return abs(diff)
        except Exception:
            return 0.0

    async def _find_source_code(self, flow: TransactionFlow, max_patterns: int) -> List[Dict[str, Any]]:
        """Use existing SQL search tools to find source code for each pattern."""
        findings = []

        # Initialize search tools
        sql_search = SQLRailsSearchTool(self.project_root)
        enhanced_search = EnhancedSQLRailsSearch(self.project_root)

        # Search for source code for each significant query
        significant_queries = [q for q in flow.queries if q.operation in ['INSERT', 'UPDATE'] and q.table]

        for query in significant_queries[:max_patterns]:
            try:
                # Use enhanced search for better results
                search_result = await enhanced_search.execute({
                    "sql": query.sql,
                    "include_usage_sites": True,
                    "max_results": 5
                })

                if search_result and not search_result.get("error"):
                    findings.append({
                        "query": f"{query.operation} {query.table}",
                        "sql": query.sql[:100] + "..." if len(query.sql) > 100 else query.sql,
                        "search_results": search_result,
                        "timestamp": query.timestamp
                    })
            except Exception as e:
                self._debug_log(f"Search failed for {query.table}: {str(e)}")
                continue

        return findings

    async def _analyze_models_in_transaction(self, flow: TransactionFlow) -> Dict[str, Any]:
        """Analyze Rails models mentioned in the transaction for callbacks and associations."""
        model_analysis = {}

        if not self.project_root:
            return model_analysis

        # Get all tables mentioned in the transaction
        tables = set(q.table for q in flow.queries if q.table)

        # Initialize model analyzer
        model_analyzer = ModelAnalyzer(self.project_root)

        for table in tables:
            # Convert table name to model name (users -> User)
            model_name = self._table_to_model_name(table)

            try:
                # Analyze the model
                result = await model_analyzer.execute({
                    "model_name": model_name,
                    "include_callbacks": True,
                    "include_associations": True
                })

                if result and not result.get("error"):
                    model_analysis[table] = {
                        "model_name": model_name,
                        "analysis": result,
                        "callbacks": self._extract_relevant_callbacks(result),
                        "associations": self._extract_relevant_associations(result)
                    }

            except Exception as e:
                self._debug_log(f"Model analysis failed for {model_name}: {str(e)}")
                continue

        return model_analysis

    def _table_to_model_name(self, table_name: str) -> str:
        """Convert table name to Rails model name."""
        if not table_name:
            return ""

        # Handle common Rails pluralizations
        singular = table_name
        if table_name.endswith("ies"):
            singular = table_name[:-3] + "y"
        elif table_name.endswith("ses"):
            singular = table_name[:-2]
        elif table_name.endswith("es") and not table_name.endswith("ses"):
            singular = table_name[:-2]
        elif table_name.endswith("s"):
            singular = table_name[:-1]

        # Convert to PascalCase
        return "".join(word.capitalize() for word in singular.split("_"))

    def _extract_relevant_callbacks(self, model_result: Dict[str, Any]) -> List[str]:
        """Extract callbacks that might be relevant to transaction analysis."""
        callbacks = []

        # Look for callback information in the model analysis result
        if "callbacks" in model_result:
            for callback_type, callback_list in model_result["callbacks"].items():
                if callback_type in ["after_create", "after_save", "after_update", "after_destroy"]:
                    callbacks.extend([f"{callback_type}: {cb}" for cb in callback_list])

        return callbacks

    def _extract_relevant_associations(self, model_result: Dict[str, Any]) -> List[str]:
        """Extract associations that might explain data relationships."""
        associations = []

        if "associations" in model_result:
            for assoc_type, assoc_list in model_result["associations"].items():
                associations.extend([f"{assoc_type}: {assoc}" for assoc in assoc_list])

        return associations

    def _generate_transaction_summary(self, flow: TransactionFlow, source_findings: List[Dict], model_analysis: Dict[str, Any] = None) -> str:
        """Generate a human-readable summary of the transaction."""
        summary_lines = []

        # Transaction overview
        summary_lines.append("=== SQL Transaction Analysis ===\n")
        summary_lines.append(f"Total queries: {len(flow.queries)}")

        tables = list(set(q.table for q in flow.queries if q.table))
        summary_lines.append(f"Tables affected: {', '.join(tables)}")

        # Operation breakdown
        ops = {}
        for query in flow.queries:
            ops[query.operation] = ops.get(query.operation, 0) + 1

        op_summary = ", ".join([f"{op}: {count}" for op, count in ops.items()])
        summary_lines.append(f"Operations: {op_summary}\n")

        # Transaction patterns identified
        if flow.rails_patterns:
            summary_lines.append("=== Transaction Patterns Detected ===")
            for pattern in flow.rails_patterns:
                summary_lines.append(f"• {pattern['pattern_type']}: {pattern['description']}")
                if 'likely_cause' in pattern:
                    summary_lines.append(f"  Likely cause: {pattern['likely_cause']}")
                if 'time_diff_ms' in pattern:
                    summary_lines.append(f"  Time difference: {pattern['time_diff_ms']:.1f}ms")
            summary_lines.append("")

        # Trigger chains
        if flow.trigger_chain:
            summary_lines.append("=== Callback/Trigger Chain ===")
            for trigger, target in flow.trigger_chain:
                summary_lines.append(f"• {trigger} → {target}")
            summary_lines.append("")

        # Model analysis findings
        if model_analysis:
            summary_lines.append("=== Rails Models Analysis ===")
            for table, info in model_analysis.items():
                summary_lines.append(f"• {table} (Model: {info['model_name']})")
                if info.get('callbacks'):
                    summary_lines.append("  Callbacks:")
                    for callback in info['callbacks'][:3]:  # Show top 3
                        summary_lines.append(f"    - {callback}")
                if info.get('associations'):
                    summary_lines.append("  Associations:")
                    for assoc in info['associations'][:3]:  # Show top 3
                        summary_lines.append(f"    - {assoc}")
                summary_lines.append("")

        # Source code findings
        if source_findings:
            summary_lines.append("=== Source Code Locations ===")
            for finding in source_findings:
                summary_lines.append(f"• {finding['query']}:")
                if finding.get('search_results', {}).get('matches'):
                    for match in finding['search_results']['matches'][:3]:  # Top 3 matches
                        summary_lines.append(f"  - {match.get('file', 'unknown')}:{match.get('line', '?')}")
                summary_lines.append("")

        return "\n".join(summary_lines)

    def _create_flow_visualization(self, flow: TransactionFlow) -> Dict[str, Any]:
        """Create a visual representation of the transaction flow."""
        return {
            "timeline": [
                {
                    "step": i + 1,
                    "timestamp": q.timestamp,
                    "operation": f"{q.operation} {q.table or 'N/A'}",
                    "references": q.references
                }
                for i, q in enumerate(flow.queries)
            ],
            "trigger_graph": [
                {"from": trigger, "to": target}
                for trigger, target in flow.trigger_chain
            ]
        }