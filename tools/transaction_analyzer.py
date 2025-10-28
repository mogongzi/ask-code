"""
SQL Transaction Analyzer Tool

Analyzes complete SQL transaction logs to understand the flow of operations
and map them to Rails/ActiveRecord patterns and source code locations.
"""
from __future__ import annotations

import re
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .base_tool import BaseTool
from .components.sql_log_extractor import AdaptiveSQLExtractor, SQLType, ExtractedSQL
from .components.sql_statement_analyzer import SQLStatementAnalyzer
from .components.rails_code_locator import RailsCodeLocator
from .semantic_sql_analyzer import SemanticSQLAnalyzer, QueryIntent
from .components.rails_inflection import table_to_model
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

    def execute(self, input_params: Dict[str, Any]) -> Any:
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
                model_analysis = self._analyze_models_in_transaction(flow)

            # Find source code if requested
            source_findings = []
            if find_source and self.project_root:
                source_findings = self._find_source_code(flow, max_patterns)

            # Generate transaction summary
            summary = self._generate_transaction_summary(flow, source_findings, model_analysis)

            # Generate callback suggestions for agent follow-up
            callback_suggestions = []
            if model_analysis:
                callback_suggestions = self._extract_callback_suggestions(model_analysis)

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
                "visualization": self._create_flow_visualization(flow),
                "callback_investigation_suggestions": callback_suggestions,  # NEW: guide agent to investigate
                "_metadata": {
                    "cacheable": True,
                    "cache_reason": "Large, stable transaction analysis result (10-100KB) used across multiple reasoning turns"
                }
            }

        except Exception as e:
            return {"error": f"Transaction analysis failed: {str(e)}"}

    def create_compact_output(self, full_result: Dict[str, Any]) -> Dict[str, Any]:
        """Create a compact summary for non-verbose mode."""
        if "error" in full_result:
            return full_result

        query_count = full_result.get("query_count", 0)
        tables = full_result.get("tables_affected", [])
        operations = full_result.get("operation_types", [])
        patterns = full_result.get("transaction_patterns", [])
        findings = full_result.get("source_code_findings", [])

        # Extract key pattern summaries
        pattern_summary = []
        for p in patterns[:3]:  # Top 3 patterns
            ptype = p.get("pattern_type", "unknown")
            if ptype == "cascade_insert":
                pattern_summary.append(f"Cascade: {' → '.join(p.get('sequence', []))}")
            elif ptype == "read_modify_write":
                pattern_summary.append(f"Read-modify-write: {p.get('table', 'unknown')}")
            elif ptype == "bulk_operation":
                pattern_summary.append(f"Bulk: {p.get('count', 0)}x {p.get('table', 'unknown')}")

        # Extract top source code finding (prioritize verified controller > transaction fingerprint)
        top_finding = None
        if findings:
            # First try to find verified controller context (highest priority)
            for f in findings:
                if f.get("search_strategy") == "controller_context_verification":
                    matches = f.get("search_results", {}).get("matches", [])
                    if matches:
                        top_finding = {
                            "file": matches[0]["file"],
                            "line": matches[0]["line"],
                            "confidence": matches[0]["confidence"],
                            "type": "verified_controller"
                        }
                        break

            # Fall back to transaction fingerprint if no controller verification
            if not top_finding:
                for f in findings:
                    if f.get("search_strategy") == "transaction_fingerprint":
                        matches = f.get("search_results", {}).get("matches", [])
                        if matches:
                            top_finding = {
                                "file": matches[0]["file"],
                                "line": matches[0]["line"],
                                "confidence": matches[0]["confidence"],
                                "type": "transaction_wrapper"
                            }
                            break

        compact = {
            "summary": f"Transaction: {query_count} queries across {len(tables)} tables",
            "tables": tables[:5] if len(tables) > 5 else tables,
            "operations": operations,
            "key_patterns": pattern_summary if pattern_summary else ["No significant patterns detected"],
        }

        if top_finding:
            compact["source_code"] = top_finding
        else:
            compact["source_code"] = "No source code matches found"

        if len(tables) > 5:
            compact["more_tables"] = f"...and {len(tables) - 5} more tables"

        if len(patterns) > 3:
            compact["more_patterns"] = f"...and {len(patterns) - 3} more patterns (use --verbose to see all)"

        compact["hint"] = "Use --verbose to see full analysis with model details, all patterns, and complete visualization"

        return compact

    def _parse_transaction_log(self, log: str) -> TransactionFlow:
        """Parse DB logs into structured queries using adaptive pre-processing."""
        extractor = AdaptiveSQLExtractor()
        extracted = extractor.extract_all_sql(log)

        queries: List[SQLQuery] = []

        if not extracted:
            # Fallback: attempt to parse strict MySQL general log entries (best-effort)
            lines = log.strip().split('\n')
            log_pattern = re.compile(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)\s+(\d+)\s+(\w+)(?:\s+(.*))?$')
            current: Optional[SQLQuery] = None
            for raw in lines:
                line = raw.strip()
                if not line:
                    continue
                m = log_pattern.match(line)
                if m:
                    # finalize previous
                    if current and current.sql:
                        # recompute using full SQL
                        current.operation = self._extract_operation(current.sql)
                        current.table = self._extract_table(current.sql, current.operation)
                        queries.append(current)
                    timestamp, conn_id, query_type, sql_part = m.groups()
                    current = SQLQuery(
                        timestamp=timestamp,
                        connection_id=conn_id,
                        query_type=query_type,
                        sql=(sql_part or '').strip(),
                        operation=self._extract_operation(sql_part or ''),
                        table=self._extract_table(sql_part or '', self._extract_operation(sql_part or '')),
                    )
                elif current:
                    current.sql += ("\n" if current.sql else "") + line
            if current and current.sql:
                current.operation = self._extract_operation(current.sql)
                current.table = self._extract_table(current.sql, current.operation)
                queries.append(current)
        else:
            # Convert extracted statements into SQLQuery entries
            analyzer = SemanticSQLAnalyzer()
            for stmt in extracted:
                # If a transaction block was extracted as a single statement, split into sub-statements
                parts = self._split_block_into_statements(stmt.sql) if stmt.sql_type == SQLType.TRANSACTION else [stmt.sql]
                for idx, part in enumerate(parts):
                    # Prefer AST analysis to determine operation and table; fall back to regex
                    analysis = None
                    try:
                        analysis = analyzer.analyze(part)
                    except Exception:
                        analysis = None

                    # Determine operation from intent or raw SQL
                    op = self._extract_operation(part)
                    if analysis:
                        if analysis.intent == QueryIntent.DATA_INSERTION:
                            op = 'INSERT'
                        elif analysis.intent == QueryIntent.DATA_UPDATE:
                            op = 'UPDATE'
                        elif analysis.intent == QueryIntent.DATA_DELETION:
                            op = 'DELETE'
                        elif analysis.intent in (QueryIntent.EXISTENCE_CHECK, QueryIntent.COUNT_AGGREGATE, QueryIntent.DATA_RETRIEVAL):
                            op = 'SELECT'
                        elif analysis.intent == QueryIntent.TRANSACTION_CONTROL:
                            # refine via raw SQL
                            part_upper = part.strip().upper()
                            if part_upper.startswith('BEGIN') or part_upper.startswith('START TRANSACTION'):
                                op = 'BEGIN'
                            elif part_upper.startswith('COMMIT'):
                                op = 'COMMIT'
                            elif part_upper.startswith('ROLLBACK'):
                                op = 'ROLLBACK'

                    # Determine table from analysis if available
                    table = None
                    if analysis and analysis.primary_table:
                        table = analysis.primary_table.name
                    else:
                        table = self._extract_table(part, op)

                    timestamp = self._parse_timestamp_from_metadata(stmt.metadata_removed) or ""
                    queries.append(SQLQuery(
                        timestamp=timestamp,
                        connection_id="",
                        query_type="Query",
                        sql=part,
                        operation=op,
                        table=table
                    ))

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
        """Extract the main SQL operation type using shared SQLStatementAnalyzer."""
        analyzer = SQLStatementAnalyzer()
        return analyzer.extract_operation(sql)

    def _extract_table(self, sql: str, operation: str) -> Optional[str]:
        """Extract a primary table name using shared SQLStatementAnalyzer."""
        analyzer = SQLStatementAnalyzer()
        return analyzer.extract_table(sql, operation)

    def _parse_timestamp_from_metadata(self, metadata: str) -> Optional[str]:
        """Extract ISO timestamp from the metadata prefix if present."""
        if not metadata:
            return None
        m = re.search(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z)', metadata)
        return m.group(1) if m else None

    def _split_block_into_statements(self, sql_block: str) -> List[str]:
        """Split a transaction block into individual statements conservatively."""
        if not sql_block:
            return []
        lines = [l for l in sql_block.split('\n') if l.strip()]
        if not lines:
            return []

        starters = (
            'SELECT', 'INSERT', 'UPDATE', 'DELETE', 'BEGIN', 'START TRANSACTION', 'COMMIT', 'ROLLBACK'
        )
        parts: List[str] = []
        buf: List[str] = []
        for line in lines:
            u = line.lstrip().upper()
            if any(u.startswith(s) for s in starters):
                if buf:
                    parts.append('\n'.join(buf))
                    buf = []
            buf.append(line)
            # End on explicit semicolon; COMMIT/ROLLBACK lines are handled by next starter or end
            if line.rstrip().endswith(';') and buf:
                parts.append('\n'.join(buf))
                buf = []
        if buf:
            parts.append('\n'.join(buf))
        return parts

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
        """Identify which queries likely triggered other queries (deduplicated)."""
        trigger_pairs = []
        seen_triggers = set()  # Track unique trigger pairs

        for i, query in enumerate(flow.queries):
            if query.operation == 'INSERT':
                # Look for subsequent queries that reference this insert
                for j in range(i + 1, len(flow.queries)):
                    next_query = flow.queries[j]

                    # Check if next query references data from this insert
                    if (next_query.references and
                        any(ref.startswith(query.table or '') for ref in next_query.references)):
                        pair = (f"{query.table}#{i}", f"{next_query.table}#{j}")
                        if pair not in seen_triggers:
                            seen_triggers.add(pair)
                            trigger_pairs.append(pair)

        flow.trigger_chain = trigger_pairs

    def _analyze_transaction_patterns(self, flow: TransactionFlow) -> None:
        """Analyze transaction patterns using generic structural analysis."""
        patterns = []

        # Pattern 1: CASCADE INSERTS - One INSERT triggers others (deduplicated)
        insert_queries = [q for q in flow.queries if q.operation == 'INSERT']
        if len(insert_queries) > 1:
            # Track unique cascade pairs to avoid duplicates
            seen_cascades = set()
            for i in range(len(insert_queries) - 1):
                time_diff = self._get_time_diff_ms(insert_queries[i].timestamp, insert_queries[i+1].timestamp)
                if time_diff < 50:
                    cascade_key = (insert_queries[i].table, insert_queries[i+1].table)
                    if cascade_key not in seen_cascades:
                        seen_cascades.add(cascade_key)
                        patterns.append({
                            "pattern_type": "cascade_insert",
                            "description": f"INSERT into {insert_queries[i].table} triggers INSERT into {insert_queries[i+1].table}",
                            "sequence": [insert_queries[i].table, insert_queries[i+1].table],
                            "likely_cause": "ActiveRecord callback (after_create, after_save) or observer"
                        })

        # Pattern 2: READ-MODIFY-WRITE - SELECT followed by UPDATE on same table (deduplicated)
        seen_rmw = set()
        for i in range(len(flow.queries) - 1):
            current = flow.queries[i]
            next_query = flow.queries[i + 1]

            if (current.operation == 'SELECT' and
                next_query.operation == 'UPDATE' and
                current.table == next_query.table):

                if current.table not in seen_rmw:
                    seen_rmw.add(current.table)
                    patterns.append({
                        "pattern_type": "read_modify_write",
                        "description": f"SELECT from {current.table} immediately followed by UPDATE",
                        "table": current.table,
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

        # Pattern 4: DATA FLOW CHAINS - Track value references (aggregated to reduce tokens)
        data_flow_summary = {}
        for i, query in enumerate(flow.queries):
            if query.references:
                for ref in query.references:
                    ref_table = ref.split('#')[0]
                    flow_key = (ref_table, query.table)
                    if flow_key not in data_flow_summary:
                        data_flow_summary[flow_key] = {"operations": set(), "count": 0}
                    data_flow_summary[flow_key]["operations"].add(query.operation)
                    data_flow_summary[flow_key]["count"] += 1

        # Convert aggregated data flows to patterns (much more compact)
        for (from_table, to_table), info in data_flow_summary.items():
            operations_str = ", ".join(sorted(info["operations"]))
            patterns.append({
                "pattern_type": "data_flow",
                "description": f"Value from {from_table} used in {to_table} operations ({info['count']} times)",
                "from_table": from_table,
                "to_table": to_table,
                "operations": list(info["operations"]),
                "count": info["count"],
                "likely_cause": "Foreign key relationship or data dependency"
            })

        # Pattern 5: CONTROLLER CONTEXT - Extract controller/action from MySQL-style comments
        for query in flow.queries:
            sql = query.sql
            # Support both quoted pairs and MySQL /* controller:Foo, action:bar */ comments
            controller_match = re.search(r"'controller'\s*[,=]\s*'([^']+)'", sql)
            action_match = re.search(r"'action'\s*[,=]\s*'([^']+)'", sql)
            if not (controller_match and action_match):
                controller_match = re.search(r"controller:([A-Za-z0-9_]+)", sql)
                action_match = re.search(r"action:([A-Za-z0-9_]+)", sql)

            if controller_match and action_match:
                ctrl = controller_match.group(1)
                act = action_match.group(1)
                patterns.append({
                    "pattern_type": "controller_context",
                    "description": f"Operation in context of {ctrl}#{act}",
                    "controller": ctrl,
                    "action": act,
                    "table": query.table,
                    "inferred_context": f"{ctrl.title().replace('_', '')}Controller#{act}",
                    "source_type": "sql_metadata",
                    "warning": "Inferred from SQL comments - not verified against actual source code"
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

    def _verify_controller_context(self, flow: TransactionFlow) -> List[Dict[str, Any]]:
        """Verify controller context from SQL metadata by searching for actual controller files.

        This converts SQL metadata hints like 'controller: work_pages, action: show_as_tab'
        into verified source code locations.
        """
        findings = []

        if not self.project_root:
            return findings

        # Extract controller context patterns from flow
        controller_patterns = [p for p in flow.rails_patterns if p.get('pattern_type') == 'controller_context']

        if not controller_patterns:
            return findings

        # Deduplicate by controller#action
        seen_contexts = set()

        for pattern in controller_patterns:
            controller = pattern.get('controller', '')
            action = pattern.get('action', '')

            context_key = f"{controller}#{action}"
            if context_key in seen_contexts:
                continue
            seen_contexts.add(context_key)

            # Use RailsCodeLocator to find controller action
            locator = RailsCodeLocator(self.project_root)
            location = locator.find_controller_action(controller, action)

            if location:
                findings.append({
                    "query": f"CONTROLLER ACTION: {controller}#{action}",
                    "sql": f"Verified from SQL metadata (controller: {controller}, action: {action})",
                    "search_results": {
                        "matches": [{
                            "file": location.file,
                            "line": location.line,
                            "snippet": f"def {action}",
                            "confidence": location.confidence,
                            "why": [
                                "SQL comment contained controller/action metadata",
                                f"Controller file: {controller}_controller.rb",
                                f"Action method: def {action}",
                                "This is the entry point that initiated the transaction"
                            ]
                        }]
                    },
                    "timestamp": flow.queries[0].timestamp if flow.queries else "",
                    "search_strategy": "controller_context_verification"
                })
            else:
                self._debug_log(f"Controller action not found: {controller}#{action}")

        return findings

    def _find_source_code(self, flow: TransactionFlow, max_patterns: int) -> List[Dict[str, Any]]:
        """Find transaction source code using multi-signal contextual search strategy.

        OPTIMIZATION: Deduplicate findings by query type + table to reduce token usage.
        """
        findings = []

        if not self.project_root:
            return findings

        # Strategy 0: Controller context verification (HIGHEST PRIORITY)
        # If SQL contains controller/action metadata, try to verify it exists
        controller_findings = self._verify_controller_context(flow)
        if controller_findings:
            findings.extend(controller_findings)
            self._debug_log(f"Controller context verification found {len(controller_findings)} matches")

        # Strategy 1: Transaction fingerprint matching (PRIMARY)
        # Find the wrapping transaction block by matching table + column signatures
        transaction_findings = self._find_transaction_wrapper(flow)
        if transaction_findings:
            findings.extend(transaction_findings)
            self._debug_log(f"Transaction wrapper search found {len(transaction_findings)} matches")

        # NOTE: Individual query pattern matching has been moved to orchestration layer.
        #
        # ARCHITECTURAL DECISION:
        # Tools should NOT call other tools directly (violates independence principle).
        # If transaction-level search finds insufficient matches, the orchestration layer
        # (react_rails_agent.py) should decide to invoke enhanced_sql_rails_search for
        # individual queries based on the transaction_analyzer output.
        #
        # This maintains clean separation: transaction_analyzer focuses on transaction flow,
        # enhanced_sql_rails_search focuses on single queries, and the agent coordinates them.

        return findings

    def _analyze_models_in_transaction(self, flow: TransactionFlow) -> Dict[str, Any]:
        """Analyze Rails models mentioned in the transaction for callbacks and associations.

        Returns compact model info (callbacks + associations only) to reduce token usage.
        """
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
                result = model_analyzer.execute({
                    "model_name": model_name,
                    "include_callbacks": True,
                    "include_associations": True
                })

                if result and not result.get("error"):
                    # OPTIMIZATION: Store only essential info, not full analysis
                    callbacks = self._extract_relevant_callbacks(result)
                    associations = self._extract_relevant_associations(result, tables)

                    # Get model file path for callback location hints
                    model_file = result.get("file_path", f"app/models/{model_name.lower()}.rb")

                    model_analysis[table] = {
                        "model_name": model_name,
                        "model_file": model_file,
                        "callbacks": callbacks,
                        "associations": associations
                        # Removed: "analysis" field that contains full verbose output
                    }

            except Exception as e:
                self._debug_log(f"Model analysis failed for {model_name}: {str(e)}")
                continue

        return model_analysis

    def _table_to_model_name(self, table_name: str) -> str:
        """Convert table name to Rails model name using shared helper."""
        return table_to_model(table_name)

    def _extract_relevant_callbacks(self, model_result: Dict[str, Any]) -> List[str]:
        """Extract callbacks that might be relevant to transaction analysis."""
        callbacks = []

        # Look for callback information in the model analysis result
        if "callbacks" in model_result:
            callback_data = model_result["callbacks"]

            # Handle both list format (from model_analyzer) and dict format
            if isinstance(callback_data, list):
                # List of callback objects with timing/event info
                for cb in callback_data:
                    if isinstance(cb, dict):
                        timing = cb.get("timing", "")
                        event = cb.get("event", "")
                        method = cb.get("method", "")
                        callback_type = f"{timing}_{event}" if timing and event else "callback"

                        if callback_type in ["after_create", "after_save", "after_update", "after_destroy"]:
                            callbacks.append(f"{callback_type}: {method}")
            elif isinstance(callback_data, dict):
                # Dict format: {callback_type: [callback_list]}
                for callback_type, callback_list in callback_data.items():
                    if callback_type in ["after_create", "after_save", "after_update", "after_destroy"]:
                        callbacks.extend([f"{callback_type}: {cb}" for cb in callback_list])

        return callbacks

    def _extract_relevant_associations(self, model_result: Dict[str, Any], tables_in_transaction: set = None) -> List[str]:
        """Extract associations that might explain data relationships.

        OPTIMIZATION: Filter to only associations involving tables in this transaction.
        """
        associations = []
        tables_in_transaction = tables_in_transaction or set()

        if "associations" in model_result:
            assoc_data = model_result["associations"]

            # Handle both list format (from model_analyzer) and dict format
            if isinstance(assoc_data, list):
                # List of association objects with type/target info
                for assoc in assoc_data:
                    if isinstance(assoc, dict):
                        assoc_type = assoc.get("type", "association")
                        target = assoc.get("target", "unknown")
                        assoc_str = f"{assoc_type}: {target}"

                        # Only include if target table is in transaction or if no filter
                        if not tables_in_transaction or any(table in target.lower() for table in tables_in_transaction):
                            associations.append(assoc_str)
            elif isinstance(assoc_data, dict):
                # Dict format: {assoc_type: [assoc_list]}
                for assoc_type, assoc_list in assoc_data.items():
                    for assoc in assoc_list:
                        assoc_str = f"{assoc_type}: {assoc}"
                        # Only include if target is in transaction
                        if not tables_in_transaction or any(table in assoc.lower() for table in tables_in_transaction):
                            associations.append(assoc_str)

        # Limit to top 5 most relevant (reduce tokens)
        return associations[:5]

    def _extract_callback_suggestions(self, model_analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Extract and verify callback methods with actual line numbers.

        Returns VERIFIED callbacks with real file:line locations, not just suggestions.
        """
        verified_callbacks = []

        for table, info in model_analysis.items():
            callbacks = info.get('callbacks', [])
            model_file = info.get('model_file', f"app/models/{info['model_name'].lower()}.rb")

            # Priority callbacks that often generate complex queries
            priority_keywords = ['save', 'create', 'commit', 'feed', 'audit', 'aggregate', 'publish']

            for callback in callbacks:
                callback_lower = callback.lower()
                if any(keyword in callback_lower for keyword in priority_keywords):
                    # Extract method name from "after_save: method_name" format
                    if ':' in callback:
                        method_name = callback.split(':')[-1].strip()

                        # Search for the CALLBACK DECLARATION line (not the method definition)
                        # This finds where "after_save :method_name" is declared, which is what we want
                        line_num = self._find_callback_declaration_line(model_file, callback)

                        if line_num:
                            # Only include if we found a real line number
                            verified_callbacks.append({
                                'table': table,
                                'model': info['model_name'],
                                'model_file': model_file,
                                'callback': callback,
                                'method_name': method_name,
                                'line': line_num,  # Real line number of callback declaration!
                                'priority': 'high',
                                'reason': 'Likely generates multiple queries (feed/audit/aggregate pattern)',
                                'verified': True
                            })
                        else:
                            # Callback declaration not found - mark as unverified suggestion
                            verified_callbacks.append({
                                'table': table,
                                'model': info['model_name'],
                                'model_file': model_file,
                                'callback': callback,
                                'method_name': method_name,
                                'line': None,
                                'priority': 'high',
                                'reason': 'Likely generates multiple queries (feed/audit/aggregate pattern)',
                                'verified': False,
                                'warning': 'Callback declaration not found in model file'
                            })

        # Return top 2 verified callbacks (or unverified if that's all we have)
        return verified_callbacks[:2]

    def _find_callback_declaration_line(self, model_file: str, callback_str: str) -> Optional[int]:
        """Search for the callback declaration line using shared RailsCodeLocator.

        This is different from finding the method definition - we want the line where the callback is registered,
        not where the callback method is implemented.
        """
        if not self.project_root:
            return None

        # Extract callback type and method name from callback_str
        # Format: "after_save: method_name" or "after_create: method_name"
        if ':' not in callback_str:
            return None

        callback_type, method_name = [part.strip() for part in callback_str.split(':', 1)]

        # Extract model name from file path for caching
        model_name = Path(model_file).stem.title().replace('_', '')

        # Use RailsCodeLocator to find callback
        locator = RailsCodeLocator(self.project_root)
        location = locator.find_callback(model_file, callback_type, method_name, model_name)

        return location.line if location else None

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

            # Add callback findings (verified with real line numbers)
            callback_suggestions = self._extract_callback_suggestions(model_analysis)
            if callback_suggestions:
                verified_callbacks = [cb for cb in callback_suggestions if cb.get('verified')]
                unverified_callbacks = [cb for cb in callback_suggestions if not cb.get('verified')]

                # Show verified callbacks first
                if verified_callbacks:
                    summary_lines.append("✅ VERIFIED Callback Methods:")
                    for cb in verified_callbacks:
                        summary_lines.append(f"  • {cb['model']}#{cb['method_name']}")
                        summary_lines.append(f"    📍 {cb['model_file']}:{cb['line']}")
                        summary_lines.append(f"    Callback: {cb['callback']}")
                        summary_lines.append(f"    Reason: {cb['reason']}")
                    summary_lines.append("")

                # Show unverified callbacks as suggestions
                if unverified_callbacks:
                    summary_lines.append("💡 SUGGESTED FOLLOW-UP (method definition not found):")
                    for cb in unverified_callbacks:
                        summary_lines.append(f"  • {cb['model']}#{cb['method_name']}")
                        summary_lines.append(f"    Callback: {cb['callback']}")
                        summary_lines.append(f"    ⚠️  {cb.get('warning', 'Not verified')}")
                        summary_lines.append(f"    📖 Search manually in {cb['model_file']}")
                    summary_lines.append("")

        # Source code findings
        if source_findings:
            summary_lines.append("=== Source Code Locations ===")

            # Separate findings by strategy (priority order)
            controller_findings = [f for f in source_findings if f.get('search_strategy') == 'controller_context_verification']
            transaction_findings = [f for f in source_findings if f.get('search_strategy') == 'transaction_fingerprint']
            query_findings = [f for f in source_findings if f.get('search_strategy') == 'individual_query']

            # Show verified controller context first (HIGHEST priority - actual entry point)
            if controller_findings:
                summary_lines.append("✅ VERIFIED Controller Entry Point:")
                for finding in controller_findings[:1]:  # Just show the main entry point
                    if finding.get('search_results', {}).get('matches'):
                        for match in finding['search_results']['matches'][:1]:
                            summary_lines.append(f"  📍 {match.get('file', 'unknown')}:{match.get('line', '?')}")
                            summary_lines.append(f"     Method: {match.get('snippet', 'N/A')}")
                            summary_lines.append(f"     Confidence: {match.get('confidence', 'unknown')}")
                            summary_lines.append(f"     Source: SQL metadata verified against actual controller file")
                summary_lines.append("")

            # Show transaction wrapper findings (high confidence code blocks)
            if transaction_findings:
                summary_lines.append("🎯 Transaction Wrapper (High Confidence):")
                for finding in transaction_findings[:2]:  # Top 2 transaction matches
                    if finding.get('search_results', {}).get('matches'):
                        for match in finding['search_results']['matches'][:1]:  # Just the top match
                            summary_lines.append(f"  📍 {match.get('file', 'unknown')}:{match.get('line', '?')}")
                            summary_lines.append(f"     Confidence: {match.get('confidence', 'unknown')}")
                            if finding.get('matched_columns'):
                                direct_cols = [c for c in finding['matched_columns'] if c not in match.get('polymorphic_columns', [])]
                                poly_cols = match.get('polymorphic_columns', [])

                                if direct_cols:
                                    summary_lines.append(f"     Matched columns: {', '.join(direct_cols[:5])}")
                                if poly_cols:
                                    summary_lines.append(f"     Polymorphic columns: {', '.join(poly_cols)} (via association)")
                summary_lines.append("")

            # Show individual query findings if available
            if query_findings:
                summary_lines.append("Individual Query Matches:")
                for finding in query_findings[:3]:  # Top 3 query matches
                    summary_lines.append(f"• {finding['query']}:")
                    if finding.get('search_results', {}).get('matches'):
                        for match in finding['search_results']['matches'][:2]:  # Top 2 matches per query
                            summary_lines.append(f"  - {match.get('file', 'unknown')}:{match.get('line', '?')}")
                summary_lines.append("")

        # Show inferred context separately (not verified)
        inferred_contexts = [p for p in flow.rails_patterns if p.get('pattern_type') == 'controller_context']
        if inferred_contexts and not any(f.get('search_strategy') == 'controller_context_verification' for f in source_findings):
            summary_lines.append("💡 Inferred Context (from SQL metadata - not verified):")
            for ctx in inferred_contexts[:1]:
                summary_lines.append(f"  • SQL comments suggest: {ctx.get('inferred_context', 'unknown')}")
                summary_lines.append(f"    ⚠️  {ctx.get('warning', 'Not verified against actual source code')}")
            summary_lines.append("")

        return "\n".join(summary_lines)

    def _find_transaction_wrapper(self, flow: TransactionFlow) -> List[Dict[str, Any]]:
        """
        Find the transaction wrapper using multi-signal search:
        1. Extract signature columns from primary INSERT
        2. Find files mentioning table + multiple signature columns
        3. Search for transaction blocks in those files
        """
        findings = []

        # Get the primary INSERT (first meaningful insert, usually the trigger)
        primary_insert = self._get_primary_insert(flow)
        if not primary_insert:
            self._debug_log("No primary INSERT found in transaction")
            return findings

        self._debug_log(f"Primary INSERT table: {primary_insert.table}")

        # Extract signature columns (distinctive, non-generic columns)
        signature_columns = self._extract_signature_columns(primary_insert)
        self._debug_log(f"Signature columns: {signature_columns}")

        if len(signature_columns) < 2:
            self._debug_log("Too few signature columns, skipping fingerprint matching")
            return findings

        # Use ripgrep to find and score transaction blocks directly
        # Dynamic threshold: scales with signature size
        # - Small signatures (3-5 cols): require 60% match (2-3 columns)
        # - Medium signatures (6-10 cols): require 40% match (3-4 columns)
        # - Large signatures (11+ cols): require 33% match (4+ columns)
        # Always require at least 3 columns to filter noise
        min_threshold = max(3, int(len(signature_columns) * 0.4))
        transaction_blocks = self._find_transaction_blocks_with_ripgrep(
            primary_insert.table,
            signature_columns,
            min_column_matches=min(min_threshold, len(signature_columns) - 1)
        )

        self._debug_log(f"Found {len(transaction_blocks)} transaction blocks")

        # Convert blocks to findings format
        for block in transaction_blocks:
            # Calculate confidence level
            raw_score = block.get('raw_score', block['score'])
            confidence_level = "very high" if raw_score >= 5 else \
                             "high" if raw_score >= 3 else "medium"

            # Build detailed match explanation
            why_lines = [
                "Transaction block wrapping table operations",
                f"Table: {primary_insert.table}",
                f"Matched columns: {', '.join(block['matched_columns'][:5])}",
                f"Column signature match: {raw_score}/{block['total_columns']}"
            ]

            # Add polymorphic association info if present
            if block.get('polymorphic_columns'):
                poly_cols = block['polymorphic_columns']
                why_lines.append(f"Polymorphic columns (via association): {', '.join(poly_cols)}")

            findings.append({
                "query": f"TRANSACTION wrapper for {primary_insert.table}",
                "sql": f"ActiveRecord::Base.transaction (wrapping {len(flow.queries)} queries)",
                "search_results": {
                    "matches": [{
                        "file": block['file'],
                        "line": block['line'],
                        "snippet": block['snippet'],
                        "confidence": f"{confidence_level} ({raw_score}/{block['total_columns']} columns)",
                        "why": why_lines,
                        "polymorphic_columns": block.get('polymorphic_columns', [])
                    }]
                },
                "timestamp": flow.queries[0].timestamp if flow.queries else "",
                "search_strategy": "transaction_fingerprint",
                "column_matches": block.get('score', 0),  # Use weighted score
                "matched_columns": block.get('matched_columns', [])
            })

        return findings

    def _get_primary_insert(self, flow: TransactionFlow) -> Optional[SQLQuery]:
        """Get the first meaningful INSERT in the transaction (usually the trigger)."""
        for query in flow.queries:
            if query.operation == 'INSERT' and query.table:
                # Skip transaction control markers
                if query.table not in ['', 'BEGIN', 'COMMIT']:
                    return query
        return None

    def _extract_signature_columns(self, insert_query: SQLQuery) -> List[str]:
        """Extract distinctive column names from INSERT query."""
        sql = insert_query.sql

        # Extract column names from INSERT INTO table (col1, col2, ...) VALUES (...)
        insert_match = re.search(r'INSERT\s+INTO\s+["`]?\w+["`]?\s*\(([^)]+)\)', sql, re.IGNORECASE)
        if not insert_match:
            return []

        columns_str = insert_match.group(1)
        # Remove backticks and quotes, split by comma
        columns = [col.strip().strip('"`') for col in columns_str.split(',')]

        # Filter out columns that are truly auto-populated and never appear in Ruby code.
        # This focuses the signature on distinctive business logic columns.
        #
        # Why filtering matters:
        # Multiple code paths can create the same table record (e.g., PageView):
        #   - lib/page_view_helper.rb: User viewing content (has referer, user_agent, more_info)
        #   - lib/demo_scenario_actions.rb: Demo data (generic PageView without context)
        #
        # Without filtering, both match on common columns (member_id, company_id, action, etc.)
        # making it hard to distinguish. Filtering focuses on distinctive attributes.
        generic_columns = {
            'id',           # Always auto-generated by database
            'created_at',   # Rails timestamp, auto-populated
            'updated_at',   # Rails timestamp, auto-populated
            'deleted_at'    # Paranoia gem, auto-populated
        }

        signature_columns = [col for col in columns if col.lower() not in generic_columns]
        return signature_columns

    def _find_transaction_blocks_with_ripgrep(
        self, table_name: str, signature_columns: List[str], min_column_matches: int
    ) -> List[Dict[str, Any]]:
        """Extract and score transaction blocks using ripgrep directly.

        This is much faster and more accurate than scanning entire files,
        as it only searches within the 30-line transaction block context.
        """
        if not self.project_root:
            return []

        import subprocess
        from pathlib import Path

        model_name = self._table_to_model_name(table_name)

        # Use ripgrep to find transaction blocks with 30 lines of context
        # IMPORTANT: Exclude test directories - tests don't generate production SQL
        cmd = [
            "rg",
            "--type", "ruby",
            "-n",  # Show line numbers
            "-A", "30",  # Get 30 lines after (transaction body)
            "--glob", "!test/**",  # Exclude test/
            "--glob", "!spec/**",  # Exclude spec/ (RSpec)
            "--glob", "!features/**",  # Exclude features/ (Cucumber)
            r"transaction\s+do",  # Match "transaction do"
            self.project_root
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode not in (0, 1):
                self._debug_log(f"Ripgrep transaction search failed: {result.stderr}")
                return []

            output_lines = result.stdout.split('\n')
            self._debug_log(f"Ripgrep found {len(output_lines)} lines in transaction blocks")

        except Exception as e:
            self._debug_log(f"Error running ripgrep: {e}")
            return []

        # Parse ripgrep output into transaction blocks
        # Format: "file:line:content" for match, "file:line-content" for context
        blocks = []
        current_block = None

        for line in output_lines:
            if not line.strip():
                continue

            # Try to parse line: "file:line:content" or "file-line-content"
            # Ripgrep format: match lines use ":", context lines use "-"
            match = re.match(r'^([^:]+?)([-:])(\d+)([-:])(.*)$', line)
            if not match:
                continue

            file_path, _sep1, line_num, separator, content = match.groups()

            # New block starts (separator is ':')
            if separator == ':' and 'transaction' in content.lower():
                if current_block:
                    blocks.append(current_block)
                current_block = {
                    'file': file_path,
                    'line': int(line_num),
                    'content_lines': [content]
                }
            elif current_block:
                # Continue current block (separator is '-')
                current_block['content_lines'].append(content)

        # Don't forget the last block
        if current_block:
            blocks.append(current_block)

        self._debug_log(f"Parsed {len(blocks)} transaction blocks")

        # Extract polymorphic associations from the model
        polymorphic_mappings = self._extract_polymorphic_associations(model_name)
        self._debug_log(f"Polymorphic mappings for {model_name}: {polymorphic_mappings}")

        # Score each block
        scored_blocks = []
        blocks_passed_filter = 0
        blocks_checked = 0

        for block in blocks:
            block_text = '\n'.join(block['content_lines'])
            blocks_checked += 1

            # REMOVED: Overly strict model/table name filter
            # The actual Ruby code might not mention "PageView" or "page_views" explicitly,
            # but we can still find it by matching signature columns (member_id, referer, etc.)

            blocks_passed_filter += 1

            # Enhanced debug for ALL blocks that pass the filter (not just page_view_helper)
            if blocks_passed_filter <= 3:  # Debug first 3 blocks
                print(f"\n🔍 DEBUG Block #{blocks_passed_filter}: {block['file']}:{block['line']}")
                print(f"   Block has {len(block['content_lines'])} lines captured")
                print(f"   Block preview (first 800 chars):\n{block_text[:800]}")
                print(f"   Searching for {len(signature_columns)} columns: {signature_columns[:5]}...")

            # Count column matches ONLY within this block
            # IMPORTANT: Also search for association names (member_id -> member)
            # because ActiveRecord associations use the association name, not the column name
            matched_columns = []
            for col in signature_columns:
                # Match as symbol (:column), hash key (column:), or quoted string
                pattern = rf'(:{col}\b|{col}:|[\'\"]{col}[\'"])'
                if re.search(pattern, block_text):
                    matched_columns.append(col)
                    if blocks_passed_filter <= 3:
                        print(f"   ✓ Matched {col} (exact)")
                # Also try association name for foreign keys (member_id -> member)
                # SQL: member_id, Ruby: :member => @logged_in_user
                elif col.endswith('_id'):
                    assoc_name = col[:-3]  # Strip _id suffix
                    assoc_pattern = rf'(:{assoc_name}\b|{assoc_name}:|[\'\"]{assoc_name}[\'"])'
                    if re.search(assoc_pattern, block_text):
                        matched_columns.append(col)
                        if blocks_passed_filter <= 3:
                            print(f"   ✓ Matched {col} via association :{assoc_name}")

            # Check for polymorphic associations in this block
            polymorphic_matched = []
            for attr_name, (type_col, id_col) in polymorphic_mappings.items():
                patterns = [
                    rf':{attr_name}\s*=>',
                    rf'{attr_name}:\s*\w',
                    rf'[\'"]{attr_name}[\'"]?\s*=>',
                ]
                for pattern in patterns:
                    if re.search(pattern, block_text):
                        if type_col in signature_columns and type_col not in matched_columns:
                            matched_columns.append(type_col)
                            polymorphic_matched.append(type_col)
                        if id_col in signature_columns and id_col not in matched_columns:
                            matched_columns.append(id_col)
                            polymorphic_matched.append(id_col)
                        break

            column_match_count = len(matched_columns)

            # Debug: Show match summary for first 3 blocks
            if blocks_passed_filter <= 3:
                print(f"   📊 Total matched: {column_match_count}/{len(signature_columns)} columns")
                print(f"   Threshold: {min_column_matches} columns required")
                if column_match_count < min_column_matches:
                    print(f"   ❌ Block rejected (not enough matches)")
                else:
                    print(f"   ✅ Block ACCEPTED!")

            # Apply bonus for distinctive columns
            distinctive_columns = {'referer', 'user_agent', 'first_view'}
            distinctive_matches = [c for c in matched_columns if c in distinctive_columns]
            weighted_score = column_match_count + (len(distinctive_matches) * 0.5)

            if column_match_count >= min_column_matches:
                scored_blocks.append({
                    'file': str(Path(block['file']).relative_to(self.project_root)),
                    'line': block['line'],
                    'snippet': block['content_lines'][0].strip() if block['content_lines'] else '',
                    'score': weighted_score,
                    'raw_score': column_match_count,
                    'matched_columns': matched_columns,
                    'polymorphic_columns': polymorphic_matched,
                    'total_columns': len(signature_columns),
                    'distinctive_matches': distinctive_matches,
                    'context_preview': '\n'.join(block['content_lines'][:5])
                })

        # Sort by weighted score (highest first)
        scored_blocks.sort(key=lambda x: x['score'], reverse=True)

        self._debug_log(f"Blocks passed table/model filter: {blocks_passed_filter}")
        self._debug_log(f"Scored {len(scored_blocks)} blocks with {min_column_matches}+ columns")
        return scored_blocks[:10]  # Return top 10 blocks

    def _extract_polymorphic_associations(self, model_name: str) -> Dict[str, Tuple[str, str]]:
        """
        Extract polymorphic association mappings from a Rails model.

        Returns a dict mapping virtual attribute name to (type_column, id_column) tuple.
        Example: {'content': ('key_type', 'key_id')}
        """
        if not self.project_root:
            return {}

        from pathlib import Path
        import re as regex_module

        # Convert PascalCase model name to snake_case filename (PageView -> page_view)
        filename = regex_module.sub(r'(?<!^)(?=[A-Z])', '_', model_name).lower()

        # Find the model file
        model_file = Path(self.project_root) / f"app/models/{filename}.rb"
        if not model_file.exists():
            return {}

        try:
            with open(model_file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            # Pattern: belongs_to :content, :polymorphic => true, :foreign_key => :key_id, :foreign_type => :key_type
            # Or: belongs_to :content, polymorphic: true, foreign_key: :key_id, foreign_type: :key_type
            # IMPORTANT: Use [^\n]*? instead of .*? to prevent matching across multiple belongs_to lines
            polymorphic_pattern = re.compile(
                r'belongs_to\s+:(\w+)[^\n]*?polymorphic[^\n]*?'
                r'foreign_key:\s*:(\w+)[^\n]*?'
                r'foreign_type:\s*:(\w+)',
                re.IGNORECASE
            )

            # Alternative pattern with hash rocket syntax
            polymorphic_pattern_rocket = re.compile(
                r'belongs_to\s+:(\w+)[^\n]*?:polymorphic\s*=>\s*true[^\n]*?'
                r':foreign_key\s*=>\s*:(\w+)[^\n]*?'
                r':foreign_type\s*=>\s*:(\w+)',
                re.IGNORECASE
            )

            mappings = {}

            # Try modern syntax first
            for match in polymorphic_pattern.finditer(content):
                attr_name, foreign_key, foreign_type = match.groups()
                mappings[attr_name] = (foreign_type, foreign_key)

            # Try hash rocket syntax
            for match in polymorphic_pattern_rocket.finditer(content):
                attr_name, foreign_key, foreign_type = match.groups()
                mappings[attr_name] = (foreign_type, foreign_key)

            return mappings

        except Exception as e:
            self._debug_log(f"Error reading model {model_name}: {e}")
            return {}

    def _detect_polymorphic_usage_in_file(
        self, file_path: str, polymorphic_mappings: Dict[str, Tuple[str, str]]
    ) -> List[str]:
        """
        Detect if a file uses any polymorphic associations.

        Returns list of physical column names that are implicitly set via polymorphic associations.
        Example: If file contains `:content => model_instance` and polymorphic_mappings has
                 {'content': ('key_type', 'key_id')}, returns ['key_type', 'key_id']
        """
        if not polymorphic_mappings:
            return []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            matched_columns = []

            for attr_name, (type_col, id_col) in polymorphic_mappings.items():
                # Look for patterns like:
                # :content => something
                # content: something
                # 'content' => something
                patterns = [
                    rf':{attr_name}\s*=>',
                    rf'{attr_name}:\s*\w',
                    rf'[\'"]{attr_name}[\'"]?\s*=>',
                ]

                for pattern in patterns:
                    if re.search(pattern, content):
                        matched_columns.extend([type_col, id_col])
                        break  # Only count once per attribute

            return list(set(matched_columns))  # Remove duplicates

        except Exception as e:
            self._debug_log(f"Error reading file {file_path}: {e}")
            return []

    def _create_flow_visualization(self, flow: TransactionFlow) -> Dict[str, Any]:
        """Create a visual representation of the transaction flow.

        OPTIMIZATION: Remove redundant timestamps and empty references to reduce tokens.
        """
        # Check if all timestamps are identical (common in logs with low precision)
        timestamps = [q.timestamp for q in flow.queries if q.timestamp]
        all_same_timestamp = len(set(timestamps)) == 1 if timestamps else False

        timeline = []
        for i, q in enumerate(flow.queries):
            step = {
                "step": i + 1,
                "operation": f"{q.operation} {q.table or 'N/A'}"
            }
            # Only include timestamp if they vary (saves tokens when all identical)
            if not all_same_timestamp and q.timestamp:
                step["timestamp"] = q.timestamp
            # Only include references if non-empty (saves tokens)
            if q.references:
                step["references"] = q.references
            timeline.append(step)

        # Deduplicate trigger graph (remove duplicate edges)
        seen_edges = set()
        unique_trigger_graph = []
        for trigger, target in flow.trigger_chain:
            edge = (trigger, target)
            if edge not in seen_edges:
                seen_edges.add(edge)
                unique_trigger_graph.append({"from": trigger, "to": target})

        return {
            "timeline": timeline,
            "trigger_graph": unique_trigger_graph
        }
