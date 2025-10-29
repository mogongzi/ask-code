"""
Intelligent SQL → Rails Code Detective

An AI-powered tool that reasons about SQL queries semantically to trace them back
to Rails source code. Handles complex patterns, transactions, and dynamic queries
through intelligent analysis rather than rigid pattern matching.

Uses SQLGlot AST parsing for true semantic understanding.
"""
from __future__ import annotations

import re
 
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from .base_tool import BaseTool
from .components.sql_log_extractor import AdaptiveSQLExtractor, SQLType
from .components.code_search_engine import CodeSearchEngine
from .components.result_ranker import ResultRanker
from .components.rails_pattern_matcher import RailsPatternMatcher
from .components.sql_log_classifier import SQLLogClassifier
from .components.progressive_search_engine import ProgressiveSearchEngine
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
        self.search_engine = CodeSearchEngine(project_root=self.project_root, debug_log=self._debug_log)
        self.ranker = ResultRanker()
        self.pattern_matcher = RailsPatternMatcher()
        # New: Progressive search engine with domain-aware rules
        self.progressive_search = ProgressiveSearchEngine(
            code_search_engine=self.search_engine,
            project_root=self.project_root or "",
            debug=debug
        )

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

        # Use SQLLogClassifier to detect transaction logs
        classifier = SQLLogClassifier()
        classification = classifier.classify(sql)

        if classification.is_transaction():
            error_result = {
                "error": "Transaction log detected. Use transaction_analyzer tool instead.",
                "suggestion": "This appears to be a complete transaction log with multiple queries. Use the transaction_analyzer tool to analyze the entire transaction flow and find related source code.",
                "detected_queries": classification.query_count,
                "classification_reason": classification.reason
            }
            self._debug_output(error_result)
            return error_result

        # Pre-process: normalize SQL from logs if needed
        extracted_stmt: Optional[str] = None
        try:
            extractor = AdaptiveSQLExtractor()
            extracted = extractor.extract_all_sql(sql)
            if extracted and len(extracted) == 1 and extracted[0].sql:
                # Exactly one statement extracted -> normalize input SQL
                extracted_stmt = extracted[0].sql.strip()
        except Exception as e:
            # Fall back silently if preprocessing fails
            self._debug_log("Log preprocessing failed", str(e))

        if extracted_stmt:
            sql = extracted_stmt

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
        ranked_matches = self.ranker.rank(all_matches, analysis)[:max_results]
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

            match_info = {
                "path": match.path,
                "line": match.line,
                "snippet": snippet,
                "confidence": match.confidence
            }

            # Include "why" details if they contain important information (missing clauses, match scores)
            if match.why:
                # Filter for important indicators
                important_why = [
                    reason for reason in match.why
                    if "missing:" in reason.lower() or
                       "matched" in reason.lower() or
                       "/" in reason  # e.g., "matched 2/3 conditions"
                ]
                if important_why:
                    match_info["details"] = important_why

            compact_matches.append(match_info)

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
                found = self.search_engine.search(pattern, "erb")
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
                found = self.search_engine.search(pattern, "erb")
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

    # Code search and ranking helpers moved to components

    def _find_definition_sites_semantic(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """
        Intelligently search for Rails code using progressive refinement.

        Uses the new ProgressiveSearchEngine with domain-aware rules
        instead of hardcoded strategy methods.
        """
        if not analysis.primary_model or not self.project_root:
            return []

        # Use progressive search with domain rules (NEW APPROACH)
        search_results = self.progressive_search.search_progressive(
            sql_analysis=analysis,
            max_results=20  # Get more results for ranking
        )

        # Convert ProgressiveSearch results to SQLMatch format
        matches = []
        for result in search_results:
            matches.append(SQLMatch(
                path=result.file,
                line=result.line,
                snippet=result.content,
                why=result.why,
                confidence=f"{result.confidence:.2f}",
                match_type="definition"
            ))

        return matches

    def _strategy_direct_patterns(self, analysis: QueryAnalysis) -> List[SQLMatch]:
        """Search for direct Rails patterns inferred from the query."""
        matches = []

        for pattern in self.pattern_matcher.patterns_for(analysis):
            # Extract searchable terms from pattern
            if ".exists?" in pattern:
                found = self.search_engine.search(r"\.exists\?\b", "rb")
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
                found = self.search_engine.search(r"\.count\b", "rb")
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
                found = self.search_engine.search(model_pattern, "rb")
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
                found = self.search_engine.search(model_pattern, "rb")
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
                    found = self.search_engine.search(build_pattern, "rb")
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
                found = self.search_engine.search(model_pattern, "rb")
                for result in found:
                    # Calculate match completeness to determine confidence
                    completeness = self._calculate_match_completeness(result["content"], analysis)

                    # Build why list with completeness details
                    why = ["where clause match", f"model: {analysis.primary_model}"]
                    if completeness["missing_clauses"]:
                        why.append(f"missing: {', '.join(completeness['missing_clauses'])}")
                    if completeness["total_conditions"] > 0:
                        why.append(f"matched {completeness['matched_conditions']}/{completeness['total_conditions']} conditions")

                    # Use calculated confidence instead of hardcoded "high"
                    conf_label = completeness["confidence"]
                    conf_detail = f"score: {completeness['completeness_score']}"

                    matches.append(SQLMatch(
                        path=result["file"],
                        line=result["line"],
                        snippet=result["content"],
                        why=why,
                        confidence=f"{conf_label} ({conf_detail})",
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
                        found = self.search_engine.search(search_pattern, "rb")
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
                    found = self.search_engine.search(r"\.order\b", "rb")
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
                found = self.search_engine.search(model_pattern, "rb")
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
            found = self.search_engine.search(scope_pattern, "rb")
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
            scope_definitions = self.search_engine.search(r"scope\s*[:\(]\s*:(\w+)", "rb")

            for scope_def in scope_definitions[:10]:
                if model_file_pattern in scope_def["file"]:
                    # Extract scope name
                    scope_match = re.search(r"scope\s*[:\(]\s*:(\w+)", scope_def["content"])
                    if scope_match:
                        scope_name = scope_match.group(1)
                        # Now search for usage of this scope
                        usage_pattern = rf"{re.escape(analysis.primary_model)}\.{re.escape(scope_name)}\b"
                        usage_found = self.search_engine.search(usage_pattern, "rb")
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
                found = self.search_engine.search(pattern, "rb")
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
                found = self.search_engine.search(pattern, "rb")
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
                    found = self.search_engine.search(pattern, "rb")
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
                    found = self.search_engine.search(pattern, "rb")
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
                    found = self.search_engine.search(pattern, "rb")
                    for result in found[:2]:  # Limit association matches
                        # Calculate match completeness
                        completeness = self._calculate_match_completeness(result["content"], analysis)

                        # Build why list with completeness details
                        why = ["association usage", f"foreign key: {condition.column.name}"]
                        if completeness["missing_clauses"]:
                            why.append(f"missing: {', '.join(completeness['missing_clauses'])}")
                        if completeness["total_conditions"] > 0:
                            why.append(f"matched {completeness['matched_conditions']}/{completeness['total_conditions']} conditions")

                        # Use calculated confidence
                        conf_label = completeness["confidence"]
                        conf_detail = f"score: {completeness['completeness_score']}"

                        matches.append(SQLMatch(
                            path=result["file"],
                            line=result["line"],
                            snippet=result["content"],
                            why=why,
                            confidence=f"{conf_label} ({conf_detail})",
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
                found = self.search_engine.search(pattern, "rb")
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
            found = self.search_engine.search(pattern, "rb")
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

    def _calculate_match_completeness(self, snippet: str, analysis: QueryAnalysis) -> Dict[str, Any]:
        """
        Calculate how completely a code snippet matches the SQL query.

        Checks:
        - WHERE conditions: Are all SQL conditions present in the code?
        - ORDER BY clause: Does code have .order() if SQL has ORDER BY?
        - LIMIT clause: Does code have .limit()/.take() if SQL has LIMIT?
        - OFFSET clause: Does code have .offset() if SQL has OFFSET?

        Args:
            snippet: Rails code snippet
            analysis: Semantic analysis of the SQL query

        Returns:
            {
                "matched_conditions": 2,
                "total_conditions": 3,
                "has_order": True/False,
                "has_limit": True/False,
                "has_offset": True/False,
                "completeness_score": 0.6,  # 0.0 to 1.0
                "confidence": "high"/"medium"/"low"/"partial"
            }
        """
        snippet_lower = snippet.lower()

        # Count WHERE conditions matched
        total_conditions = len(analysis.where_conditions)
        matched_conditions = 0

        for condition in analysis.where_conditions:
            col_name = condition.column.name.lower()  # Normalize to lowercase
            # Check if column appears in the snippet
            # Handle both hash syntax (:column_name =>) and keyword syntax (column_name:)
            if (col_name in snippet_lower or
                f":{col_name}" in snippet_lower or
                f"{col_name}:" in snippet_lower):
                matched_conditions += 1

        # Check for ORDER BY clause
        sql_has_order = analysis.has_order or "order by" in analysis.raw_sql.lower()
        code_has_order = ".order(" in snippet_lower or ".order " in snippet_lower

        # Check for LIMIT clause
        sql_has_limit = analysis.has_limit or "limit" in analysis.raw_sql.lower()
        code_has_limit = (
            ".limit(" in snippet_lower or
            ".take(" in snippet_lower or
            ".first" in snippet_lower or
            ".last" in snippet_lower
        )

        # Check for OFFSET clause
        sql_has_offset = "offset" in analysis.raw_sql.lower()
        code_has_offset = ".offset(" in snippet_lower

        # Calculate completeness score
        score = 0.0
        weights = {
            "conditions": 0.5,  # WHERE conditions are most important
            "order": 0.2,
            "limit": 0.15,
            "offset": 0.15
        }

        # WHERE conditions score
        if total_conditions > 0:
            condition_score = matched_conditions / total_conditions
            score += condition_score * weights["conditions"]
        else:
            score += weights["conditions"]  # No conditions = full score for this part

        # ORDER BY score
        if sql_has_order:
            if code_has_order:
                score += weights["order"]
        else:
            score += weights["order"]  # No ORDER BY needed = full score

        # LIMIT score
        if sql_has_limit:
            if code_has_limit:
                score += weights["limit"]
        else:
            score += weights["limit"]  # No LIMIT needed = full score

        # OFFSET score
        if sql_has_offset:
            if code_has_offset:
                score += weights["offset"]
        else:
            score += weights["offset"]  # No OFFSET needed = full score

        # Determine confidence based on completeness
        if score >= 0.9:
            confidence = "high"
        elif score >= 0.7:
            confidence = "medium"
        elif score >= 0.4:
            confidence = "partial"
        else:
            confidence = "low"

        return {
            "matched_conditions": matched_conditions,
            "total_conditions": total_conditions,
            "has_order": code_has_order if sql_has_order else None,
            "has_limit": code_has_limit if sql_has_limit else None,
            "has_offset": code_has_offset if sql_has_offset else None,
            "completeness_score": round(score, 2),
            "confidence": confidence,
            "missing_clauses": self._identify_missing_clauses(
                sql_has_order, code_has_order,
                sql_has_limit, code_has_limit,
                sql_has_offset, code_has_offset,
                matched_conditions, total_conditions
            )
        }

    def _identify_missing_clauses(
        self,
        sql_has_order: bool, code_has_order: bool,
        sql_has_limit: bool, code_has_limit: bool,
        sql_has_offset: bool, code_has_offset: bool,
        matched_conditions: int, total_conditions: int
    ) -> List[str]:
        """Identify which SQL clauses are missing from the code match."""
        missing = []

        if total_conditions > 0 and matched_conditions < total_conditions:
            missing_count = total_conditions - matched_conditions
            missing.append(f"{missing_count} WHERE condition(s)")

        if sql_has_order and not code_has_order:
            missing.append("ORDER BY")

        if sql_has_limit and not code_has_limit:
            missing.append("LIMIT")

        if sql_has_offset and not code_has_offset:
            missing.append("OFFSET")

        return missing

    # Legacy search helpers removed (replaced by semantic strategies)

    # Legacy search helpers removed (existence patterns)

    # Legacy search helpers removed (count patterns)

    # Legacy search helpers removed (insertion patterns)

    # Legacy search helpers removed (update patterns)

    # Legacy search helpers removed (association patterns)

    # Legacy search helpers removed (callback patterns)
