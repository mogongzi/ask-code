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
from util.sql_log_extractor import AdaptiveSQLExtractor, SQLType
from .semantic_sql_analyzer import (
    SemanticSQLAnalyzer,
    QueryAnalysis,
    QueryIntent,
    create_fingerprint
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

    def __init__(self, project_root: Optional[str] = None, debug: bool = False):
        super().__init__(project_root, debug)
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

    def execute(self, input_params: Dict[str, Any]) -> Any:
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

        # Pre-process: normalize SQL from logs if needed
        extracted_stmt: Optional[str] = None
        try:
            extractor = AdaptiveSQLExtractor()
            extracted = extractor.extract_all_sql(sql)
            if extracted:
                # Multiple statements -> likely a transaction log; hand off to transaction analyzer
                if len(extracted) > 1 or extracted[0].sql_type == SQLType.TRANSACTION:
                    error_result = {
                        "error": "Transaction log detected. Use transaction_analyzer tool instead.",
                        "suggestion": "This appears to be a complete transaction log with multiple queries. Use the transaction_analyzer tool to analyze the entire transaction flow and find related source code.",
                        "detected_queries": len(extracted)
                    }
                    self._debug_output(error_result)
                    return error_result
                # Exactly one statement extracted -> normalize input SQL
                if extracted[0].sql:
                    extracted_stmt = extracted[0].sql.strip()
        except Exception as e:
            # Fall back silently if preprocessing fails
            self._debug_log("Log preprocessing failed", str(e))

        if extracted_stmt:
            sql = extracted_stmt
        else:
            # Legacy detection for transaction-like logs
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
        definition_matches = self._find_definition_sites_semantic(analysis)
        self._debug_log("📍 Definition matches found", len(definition_matches))

        # Find usage sites
        usage_matches = []
        if include_usage and definition_matches:
            self._debug_log("🔍 Finding usage sites for matches")
            usage_matches = self._find_usage_sites(definition_matches)
            self._debug_log("📍 Usage matches found", len(usage_matches))

        # Combine and rank matches
        all_matches = definition_matches + usage_matches
        self._debug_log("🏆 Ranking matches", f"{len(all_matches)} total matches")
        ranked_matches = self._rank_matches(all_matches, analysis)[:max_results]
        self._debug_log("✅ Final ranked matches", len(ranked_matches))

        # Build full result
        full_result = {
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

        self._debug_output(full_result)

        # Return compact or full result based on debug mode
        if self.debug_enabled:
            return full_result
        else:
            return self._create_compact_result(full_result, ranked_matches)

    def _create_compact_result(self, full_result: Dict[str, Any], ranked_matches: List[SQLMatch]) -> Dict[str, Any]:
        """Create a compact, user-friendly result for non-verbose mode."""
        matches_count = len(ranked_matches)

        # Show top 3 matches with truncated snippets
        compact_matches = []
        for match in ranked_matches[:3]:
            snippet = match.snippet
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            compact_matches.append({
                "path": match.path,
                "line": match.line,
                "snippet": snippet,
                "confidence": match.confidence
            })

        result = {
            "summary": f"Found {matches_count} match{'es' if matches_count != 1 else ''}",
            "fingerprint": full_result["fingerprint"],
            "top_matches": compact_matches
        }

        # Add a hint if there are more matches
        if matches_count > 3:
            result["more_matches"] = f"{matches_count - 3} more match{'es' if matches_count - 3 != 1 else ''} (use --verbose to see all)"

        return result

    def _find_usage_sites(self, definition_matches: List[SQLMatch]) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "erb")
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
                found = self._search_pattern(pattern, "erb")
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

    def _search_pattern(self, pattern: str, file_ext: str) -> List[Dict[str, Any]]:
        """Execute ripgrep search for a pattern."""
        if not self.project_root:
            self._debug_log("❌ No project root set")
            return []

        cmd = [
            "rg", "--line-number", "--with-filename", "-i",
            "--type-add", f"target:*.{file_ext}",
            "--type", "target",
            # Respect .gitignore but don't exclude common code directories
            # This avoids searching node_modules, tmp, log, etc. while still finding lib/, vendor/
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
                            rel_path = self._rel_path(file_path)
                            # Skip test files - production SQL doesn't come from tests
                            if self._is_test_file(rel_path):
                                continue
                            matches.append({
                                "file": rel_path,
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

    def _rel_path(self, file_path: str) -> str:
        """Convert absolute path to relative path."""
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

    def _is_test_file(self, file_path: str) -> bool:
        """Check if a file is a test file (production SQL doesn't come from tests)."""
        # Normalize path separators
        path_lower = file_path.lower().replace('\\', '/')

        # Common test directory patterns
        test_patterns = [
            '/test/',
            '/tests/',
            '/spec/',
            '/specs/',
            '_test.rb',
            '_spec.rb',
            'test_helper.rb',
            'spec_helper.rb'
        ]

        return any(pattern in path_lower for pattern in test_patterns)

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

    def _find_definition_sites_semantic(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Intelligently search for Rails code using semantic analysis and adaptive strategies."""
        if not analysis.primary_model or not self.project_root:
            return []

        # Use multiple adaptive search strategies
        strategies = [
            self._strategy_direct_patterns,
            self._strategy_scope_based,  # New: search for scope definitions and usage
            self._strategy_intent_based,
            self._strategy_association_based,
            self._strategy_validation_based,
            self._strategy_callback_based
        ]

        all_matches = []
        for strategy in strategies:
            matches = strategy(analysis)
            all_matches.extend(matches)

        return all_matches

    def _strategy_direct_patterns(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for direct Rails patterns inferred from the query."""
        matches = []

        for pattern in analysis.rails_patterns:
            # Extract searchable terms from pattern
            if ".exists?" in pattern:
                found = self._search_pattern(r"\.exists\?\b", "rb")
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
                found = self._search_pattern(r"\.count\b", "rb")
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

            elif ".create" in pattern or "create(" in pattern:
                # Search for Model.create(...) patterns
                model_pattern = rf"{re.escape(analysis.primary_model)}\.create\b"
                found = self._search_pattern(model_pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["create pattern match", f"matches {pattern}"],
                        confidence="high (direct match)",
                        match_type="definition"
                    ))

            elif ".new" in pattern or "new(" in pattern:
                # Search for Model.new(...).save patterns
                # We need to check if .save or .save! appears near the .new call
                # First, just add all .new matches - they're likely create operations
                model_pattern = rf"{re.escape(analysis.primary_model)}\.new\b"
                found = self._search_pattern(model_pattern, "rb")
                for result in found:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["new instance pattern", f"matches {pattern}"],
                        confidence="medium (new without confirmed save)",
                        match_type="definition"
                    ))

            elif "build_" in pattern:
                # Search for build_association patterns
                # Extract association name from pattern like "build_page_view(...)"
                build_match = re.search(r'build_(\w+)', pattern)
                if build_match:
                    assoc = build_match.group(1)
                    build_pattern = rf"build_{re.escape(assoc)}\b"
                    found = self._search_pattern(build_pattern, "rb")
                    for result in found:
                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=["build association match", f"matches {pattern}"],
                            confidence="medium (association build)",
                            match_type="definition"
                        ))

            elif ".where" in pattern:
                model_pattern = rf"{re.escape(analysis.primary_model)}\.where\b"
                found = self._search_pattern(model_pattern, "rb")
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
                        found = self._search_pattern(search_pattern, "rb")
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
                    found = self._search_pattern(r"\.order\b", "rb")
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

            elif ".take" in pattern:
                # Search for .take pattern (LIMIT queries)
                model_pattern = rf"{re.escape(analysis.primary_model)}\..*\.take\b"
                found = self._search_pattern(model_pattern, "rb")
                for result in found[:5]:
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["take pattern match (LIMIT)", f"model: {analysis.primary_model}"],
                        confidence="high (limit match)",
                        match_type="definition"
                    ))

        return matches[:10]  # Limit direct matches

    def _strategy_scope_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for scope definitions and usage based on WHERE conditions."""
        matches = []

        if not analysis.where_conditions:
            return matches

        # Extract column names from WHERE conditions
        where_columns = [cond.column.name for cond in analysis.where_conditions]

        # Search for scope definitions in model files that reference these columns
        for column in where_columns:
            # Pattern 1: scope :scope_name, -> { where(column: ...) }
            scope_pattern = rf"scope\s*[:\(]\s*:\w+.*where.*{re.escape(column)}"
            found = self._search_pattern(scope_pattern, "rb")
            for result in found[:3]:
                if analysis.primary_model.lower() in result["file"].lower() or \
                   analysis.primary_table.name in result["file"].lower():
                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=["scope definition", f"filters by {column}"],
                        confidence="high (scope definition)",
                        match_type="definition"
                    ))

            # Pattern 2: Search for scope usage like Model.scope_name(...).take
            # First find all scopes defined for this model
            model_file_pattern = analysis.primary_table.name + ".rb"
            scope_definitions = self._search_pattern(r"scope\s*[:\(]\s*:(\w+)", "rb")

            for scope_def in scope_definitions[:10]:
                if model_file_pattern in scope_def["file"]:
                    # Extract scope name
                    scope_match = re.search(r"scope\s*[:\(]\s*:(\w+)", scope_def["content"])
                    if scope_match:
                        scope_name = scope_match.group(1)
                        # Now search for usage of this scope
                        usage_pattern = rf"{re.escape(analysis.primary_model)}\.{re.escape(scope_name)}\b"
                        usage_found = self._search_pattern(usage_pattern, "rb")
                        for usage in usage_found[:3]:
                            matches.append(SQLMatch(
                                path=usage["file"],
                                line=usage["line"],
                                snippet=usage["content"],
                                why=["scope usage", f"calls {scope_name} scope"],
                                confidence="high (scope usage)",
                                match_type="definition"
                            ))

        return matches

    def _strategy_intent_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search based on query semantic intent."""
        matches = []

        if analysis.intent == QueryIntent.EXISTENCE_CHECK:
            # Search for existence patterns
            patterns = [r"\.exists\?\b", r"\.any\?\b", r"\.present\?\b", r"\.empty\?\b"]
            for pattern in patterns:
                found = self._search_pattern(pattern, "rb")
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
                found = self._search_pattern(pattern, "rb")
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

        elif analysis.intent == QueryIntent.DATA_INSERTION:
            # Search for INSERT patterns: .create, .new + .save, build_*
            if analysis.primary_model:
                model = analysis.primary_model
                # Search for Model.create or Model.new patterns
                patterns = [
                    (rf"{re.escape(model)}\.create\b", "create pattern"),
                    (rf"{re.escape(model)}\.new\b", "new instance pattern"),
                    (r"\.save!?\b", "save pattern")
                ]
                for pattern, description in patterns:
                    found = self._search_pattern(pattern, "rb")
                    for result in found[:5]:  # Limit per pattern
                        # For .save, check if model is mentioned nearby
                        if description == "save pattern":
                            if model.lower() in result["content"].lower():
                                matches.append(SQLMatch(
                                    path=result["file"],
                                    line=result["line"],
                                    snippet=result["content"],
                                    why=["insert operation", description, f"model: {model}"],
                                    confidence="high (insert pattern)",
                                    match_type="definition"
                                ))
                        else:
                            matches.append(SQLMatch(
                                path=result["file"],
                                line=result["line"],
                                snippet=result["content"],
                                why=["insert operation", description, f"model: {model}"],
                                confidence="high (insert pattern)",
                                match_type="definition"
                            ))

        elif analysis.intent == QueryIntent.DATA_UPDATE:
            # Search for UPDATE patterns
            if analysis.primary_model:
                model = analysis.primary_model
                patterns = [
                    (rf"{re.escape(model)}\.update\b", "update method"),
                    (rf"{re.escape(model)}\.update_all\b", "bulk update"),
                    (r"\.save\b", "save after modification")
                ]
                for pattern, description in patterns:
                    found = self._search_pattern(pattern, "rb")
                    for result in found[:3]:
                        if model.lower() in result["content"].lower():
                            matches.append(SQLMatch(
                                path=result["file"],
                                line=result["line"],
                                snippet=result["content"],
                                why=["update operation", description, f"model: {model}"],
                                confidence="medium (update pattern)",
                                match_type="definition"
                            ))

        return matches

    def _strategy_association_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
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
                    found = self._search_pattern(pattern, "rb")
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

    def _strategy_validation_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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

    def _strategy_callback_based(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for callbacks that might indirectly trigger queries."""
        matches = []

        callback_patterns = [
            r"after_create\b",
            r"before_save\b",
            r"after_commit\b",
            r"after_update\b"
        ]

        for pattern in callback_patterns:
            found = self._search_pattern(pattern, "rb")
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

    def _search_rails_pattern(self, pattern_desc: str, sql_info: Dict) -> List[SQLMatch]:
        """Search for specific Rails patterns."""
        matches = []

        # Extract searchable terms from pattern description
        if "exists?" in pattern_desc:
            # Search for .exists? usage
            found = self._search_pattern(r"\.exists\?", "rb")
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
            found = self._search_pattern(r"\.count\b", "rb")
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
                found = self._search_pattern(pattern, "rb")
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

    def _search_existence_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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
                found = self._search_pattern(pattern, "rb")
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

    def _search_count_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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

    def _search_insertion_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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

    def _search_update_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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

    def _search_association_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                        found = self._search_pattern(pattern, "rb")
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

    def _search_callback_patterns(self, sql_info: Dict) -> List[SQLMatch]:
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
                found = self._search_pattern(pattern, "rb")
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