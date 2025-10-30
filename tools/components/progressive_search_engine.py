"""
Progressive Refinement Search Engine

Implements generalizable SQL-to-Rails code search using progressive refinement:

1. Parse SQL for distinctive signals (table, filters, pagination, sorting)
2. Rank patterns by distinctiveness (rare → common)
3. Search in priority order, refining results
4. Validate completeness (all SQL clauses accounted for)
5. Return matches with confidence scores

Uses heuristic-based distinctiveness ranking and domain-aware search rules.
No hardcoded patterns - works for ANY SQL query.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass
from pathlib import Path

from .rails_search_rules import (
    RailsSearchRuleSet,
    RailsSearchRule,
    SearchPattern,
    SearchLocation
)
from .model_scope_analyzer import ModelScopeAnalyzer
from .sql_scope_matcher import SQLToScopeMatcher
from .where_clause_matcher import WhereClauseMatcher, WhereClauseParser
from .unified_confidence_scorer import UnifiedConfidenceScorer, ClausePresence
from .rails_inflection import singularize


@dataclass
class SearchResult:
    """A code match from progressive search."""
    file: str
    line: int
    content: str
    matched_patterns: List[str]
    confidence: float
    why: List[str]


class ProgressiveSearchEngine:
    """
    Progressive refinement search engine for Rails code discovery.

    Uses domain-aware rules and heuristic-based distinctiveness ranking
    to find Rails code that generates SQL queries.
    """

    def __init__(self, code_search_engine, project_root: str, debug: bool = False):
        """
        Initialize progressive search engine.

        Args:
            code_search_engine: CodeSearchEngine instance for executing searches
            project_root: Rails project root directory
            debug: Enable debug logging
        """
        self.search_engine = code_search_engine
        self.project_root = project_root
        self.debug = debug
        self.rule_set = RailsSearchRuleSet()
        self.where_matcher = WhereClauseMatcher(project_root=project_root)
        self.confidence_scorer = UnifiedConfidenceScorer()

    def _singularize_table_name(self, table_name: str) -> str:
        """
        Convert Rails table name (plural) to model file name (singular).

        Uses Rails ActiveSupport inflection rules for accurate singularization.

        Examples:
            members -> member
            companies -> company
            people -> person
            analyses -> analysis
        """
        return singularize(table_name)

    def search_progressive(
        self,
        sql_analysis: Any,
        max_results: int = 10
    ) -> List[SearchResult]:
        """
        Search for Rails code using progressive refinement strategy.

        Steps:
        1. Extract distinctive patterns from SQL (using heuristics)
        2. Get applicable domain rules for this SQL
        3. Search in priority order (rare → common patterns)
        4. Refine results through intersection (search-and-filter)
        5. Validate completeness (all SQL clauses present)
        6. Return top matches with confidence scores

        Args:
            sql_analysis: SemanticSQLAnalyzer result
            max_results: Maximum results to return

        Returns:
            List of SearchResult objects, ranked by confidence
        """
        if self.debug:
            print(f"\n🔍 Progressive Search for {sql_analysis.primary_table.name}")

        # Step 0: Try semantic scope matching first (NEW!)
        semantic_patterns = self._try_semantic_matching(sql_analysis)

        # Step 1: Get applicable domain rules
        applicable_rules = self.rule_set.get_applicable_rules(sql_analysis)
        if self.debug:
            print(f"   Applicable rules: {[type(r).__name__ for r in applicable_rules]}")

        # Step 2: Build and rank all search patterns
        if semantic_patterns:
            if self.debug:
                print(f"   ✓ Semantic match found: using scope-based search")
            # Combine semantic patterns (high priority) with rule patterns (fallback)
            all_patterns = semantic_patterns + self._collect_and_rank_patterns(applicable_rules, sql_analysis)
        else:
            if self.debug:
                print(f"   → No semantic match: using pattern-based search")
            # Use only pattern-based approach
            all_patterns = self._collect_and_rank_patterns(applicable_rules, sql_analysis)
        if self.debug:
            print(f"   Collected {len(all_patterns)} search patterns")
            for p in all_patterns[:5]:
                print(f"      - {p.description} (distinctiveness: {p.distinctiveness})")

        # Step 3: Progressive search with refinement
        results = self._search_with_progressive_refinement(
            all_patterns,
            applicable_rules,
            sql_analysis
        )

        # Step 4: Validate and score matches
        validated_results = self._validate_and_score(results, sql_analysis, applicable_rules)

        # Step 5: Return top results
        validated_results.sort(key=lambda r: r.confidence, reverse=True)
        return validated_results[:max_results]

    def _collect_and_rank_patterns(
        self,
        rules: List[RailsSearchRule],
        sql_analysis: Any
    ) -> List[SearchPattern]:
        """
        Collect search patterns from all rules and rank by distinctiveness.

        Distinctiveness heuristics:
        - LIMIT with specific value: 0.9 (very rare)
        - Constants (COND, CONDITION): 0.8 (rare)
        - OFFSET: 0.7 (moderately rare)
        - Scope definitions: 0.6 (moderate)
        - Generic method calls (.limit, .order): 0.4-0.5 (common)

        Returns patterns sorted by distinctiveness (highest first).
        """
        all_patterns = []

        for rule in rules:
            patterns = rule.build_search_patterns(sql_analysis)
            all_patterns.extend(patterns)

        # Deduplicate patterns: group by pattern string, keep highest distinctiveness
        pattern_dict = {}
        duplicates_eliminated = 0

        for p in all_patterns:
            key = (p.pattern, p.clause_type)  # Use pattern + clause_type as key

            if key not in pattern_dict:
                pattern_dict[key] = p
            else:
                duplicates_eliminated += 1
                existing = pattern_dict[key]

                # Keep the one with higher distinctiveness
                if p.distinctiveness > existing.distinctiveness:
                    # Merge descriptions
                    merged_desc = f"{p.description} (also: {existing.description})"
                    pattern_dict[key] = SearchPattern(
                        pattern=p.pattern,
                        distinctiveness=p.distinctiveness,
                        description=merged_desc,
                        clause_type=p.clause_type
                    )
                else:
                    # Keep existing, but merge descriptions
                    merged_desc = f"{existing.description} (also: {p.description})"
                    pattern_dict[key] = SearchPattern(
                        pattern=existing.pattern,
                        distinctiveness=existing.distinctiveness,
                        description=merged_desc,
                        clause_type=existing.clause_type
                    )

        deduplicated_patterns = list(pattern_dict.values())

        if self.debug and duplicates_eliminated > 0:
            print(f"   ⚡ Eliminated {duplicates_eliminated} duplicate patterns (before: {len(all_patterns)}, after: {len(deduplicated_patterns)})")

        # Sort by distinctiveness (rare → common)
        deduplicated_patterns.sort(key=lambda p: p.distinctiveness, reverse=True)

        return deduplicated_patterns

    def _search_with_progressive_refinement(
        self,
        patterns: List[SearchPattern],
        rules: List[RailsSearchRule],
        sql_analysis: Any
    ) -> List[Dict[str, Any]]:
        """
        Execute progressive search with refinement.

        Strategy:
        1. Start with most distinctive pattern
        2. If results < threshold (e.g., 10), we found distinctive matches
        3. Refine those results by filtering for additional patterns (FILE-LEVEL)
        4. If too many results, try next distinctive pattern
        5. Repeat until sufficient matches found or patterns exhausted

        This implements search-and-filter WITHOUT hardcoded patterns.
        """
        if self.debug:
            print(f"\n📍 Step-by-step progressive search:")

        results = []
        search_locations = self._get_merged_search_locations(rules)

        # Step 1: Search for most distinctive pattern first
        for i, pattern in enumerate(patterns):
            if self.debug:
                print(f"\n   Step {i+1}: Searching for '{pattern.description}'")

            # Execute search across relevant locations
            pattern_results = self._execute_pattern_search(
                pattern,
                search_locations,
                sql_analysis
            )

            if self.debug:
                print(f"      Found {len(pattern_results)} initial matches")

            # If this is a distinctive pattern (or moderate) and we have results, refine them
            # Updated logic: Use FILE-LEVEL refinement for many results
            if pattern.distinctiveness >= 0.4 and len(pattern_results) > 0:
                if len(pattern_results) < 20:
                    if self.debug:
                        print(f"      ✓ Found {len(pattern_results)} results, refining...")
                else:
                    if self.debug:
                        print(f"      ⚠ Found {len(pattern_results)} results (many), using file-level refinement...")

                # Use file-level refinement for better accuracy
                refined = self._refine_results_file_level(
                    pattern,
                    patterns[i+1:],  # Use remaining patterns as filters
                    search_locations,
                    sql_analysis
                )

                if self.debug:
                    print(f"      Refined to {len(refined)} matches")

                # If refinement found matches, use them and continue searching
                # (don't break - we want to find both definition AND usage sites)
                if refined:
                    results.extend(refined)
                    if self.debug:
                        print(f"      ✓ Found refined matches, continuing to search for more patterns...")
                elif len(pattern_results) < 20:
                    # No refinement helped, but we have few results - use them anyway
                    if self.debug:
                        print(f"      Using unrefined results (refinement found nothing)")
                    results.extend(pattern_results)
                else:
                    # Too many results and refinement didn't help, try next pattern
                    if self.debug:
                        print(f"      ❌ Refinement didn't help, trying next pattern")
                    continue

                # Continue to next pattern if we haven't found usage sites yet
                # (important for Rails where scope definition and usage are in different files)

            # Pattern has low distinctiveness or no results
            elif len(pattern_results) >= 100:
                # Way too many results with low distinctiveness, skip
                if self.debug:
                    print(f"      ❌ Too many results ({len(pattern_results)}), trying next pattern")
                continue

            # Few results with low distinctiveness - might still be useful
            elif len(pattern_results) > 0:
                if self.debug:
                    print(f"      ✓ Found {len(pattern_results)} matches (low distinctiveness)")
                results.extend(pattern_results)

        # Deduplicate results by file:line
        deduplicated = self._deduplicate_results(results)

        if self.debug:
            print(f"\n   Final: {len(deduplicated)} unique matches after deduplication")

        return deduplicated

    def _execute_pattern_search(
        self,
        pattern: SearchPattern,
        locations: List[SearchLocation],
        sql_analysis: Any
    ) -> List[Dict[str, Any]]:
        """
        Execute search for a pattern across all relevant locations.

        Returns raw results with file, line, content.
        """
        all_results = []

        for location in locations:
            # Search in this location
            search_results = self._search_in_location(
                pattern.pattern,
                location.glob_pattern,
                sql_analysis
            )

            # Tag results with matched pattern
            for result in search_results:
                result["matched_patterns"] = [pattern.description]
                result["pattern_type"] = pattern.clause_type

            all_results.extend(search_results)

        return all_results

    def _search_in_location(
        self,
        pattern: str,
        glob_pattern: str,
        sql_analysis: Any
    ) -> List[Dict[str, Any]]:
        """
        Search for pattern in a specific location (glob pattern).

        Uses CodeSearchEngine to execute ripgrep search.
        """
        # Extract file extension from glob (app/models/**/*.rb → rb)
        file_ext = self._extract_file_extension(glob_pattern)

        # Execute search using code_search_engine
        try:
            results = self.search_engine.search(pattern, file_ext)
            return results
        except Exception as e:
            if self.debug:
                print(f"      Search error for '{pattern}': {e}")
            return []

    def _refine_results(
        self,
        initial_results: List[Dict[str, Any]],
        additional_patterns: List[SearchPattern],
        sql_analysis: Any
    ) -> List[Dict[str, Any]]:
        """
        Refine results by filtering for additional patterns (LINE-LEVEL).

        DEPRECATED: This method does line-level filtering which is less effective.
        Use _refine_results_file_level instead for better accuracy.

        This is the search-and-filter approach (NOT hardcoded regex).

        Example:
        - Initial: Found 5 files with "500" (LIMIT value)
        - Filter: Keep only files that also contain "Member.active"
        - Filter: Keep only files that also contain "offset"
        - Result: 1-2 files that match all patterns

        This works for ANY SQL query, not just specific cases.
        """
        refined = initial_results

        # Use top 3 additional patterns for refinement (avoid over-filtering)
        refinement_patterns = additional_patterns[:3]

        for pattern in refinement_patterns:
            if not refined:
                break  # No results left to refine

            if self.debug:
                print(f"         Filtering for '{pattern.description}' ({len(refined)} results)")

            # Filter results that contain this pattern
            filtered = []
            for result in refined:
                content = result.get("content", "")

                # Check if pattern matches the content
                if self._pattern_matches(pattern.pattern, content):
                    # Add this pattern to matched list
                    result["matched_patterns"] = result.get("matched_patterns", []) + [pattern.description]
                    filtered.append(result)

            refined = filtered

            if self.debug:
                print(f"         → {len(refined)} results remaining")

        return refined

    def _refine_results_file_level(
        self,
        initial_pattern: SearchPattern,
        additional_patterns: List[SearchPattern],
        search_locations: List[SearchLocation],
        sql_analysis: Any
    ) -> List[Dict[str, Any]]:
        """
        Refine results using FILE-LEVEL filtering.

        This is more effective than line-level filtering because refinement patterns
        may appear on different lines than the initial pattern.

        Strategy:
        1. Search for initial pattern across locations
        2. Extract unique file paths from results
        3. For each file, check if it contains complementary patterns (not alternatives)
        4. Return results from files that match patterns

        Example:
        - Initial: "500" finds 1650 lines across 200 files
        - File filter: Keep files with ".limit(" → 15 files
        - File filter: Keep files with "Member" → 3 files
        - Return: All lines from those 3 files matching initial pattern
        """
        if not additional_patterns:
            # No refinement needed, return empty
            return []

        # Select complementary patterns for refinement (NOT alternatives of same type)
        # For scope chains, we want different clause types, not different scope names
        refinement_patterns = []
        seen_clause_types = {initial_pattern.clause_type}

        for p in additional_patterns:
            # Skip patterns of the same clause type as initial pattern
            # (e.g., if initial is "Member.active.limit", skip "Member.enabled.limit")
            if p.clause_type == initial_pattern.clause_type:
                continue

            # Skip if we already have a pattern of this clause type
            if p.clause_type in seen_clause_types:
                continue

            # Add this complementary pattern
            refinement_patterns.append(p)
            seen_clause_types.add(p.clause_type)

            # Use top 3 complementary patterns
            if len(refinement_patterns) >= 3:
                break

        # If no complementary patterns found, don't refine
        if not refinement_patterns:
            if self.debug:
                print(f"         No complementary patterns found, skipping refinement")
            return []

        if self.debug:
            print(f"         Using file-level filtering with {len(refinement_patterns)} complementary patterns:")
            for p in refinement_patterns:
                optional_tag = " [OPTIONAL]" if p.optional else ""
                print(f"            - {p.description} (type: {p.clause_type}){optional_tag}")

        # Execute file-level search for each location
        all_refined_results = []

        for location in search_locations:
            file_ext = self._extract_file_extension(location.glob_pattern)

            # Use the new file-level filter method from CodeSearchEngine
            # Pass SearchPattern objects (not just strings) to preserve optional flag
            refined = self.search_engine.search_file_level_filter(
                initial_pattern.pattern,
                refinement_patterns,  # Pass full SearchPattern objects
                file_ext
            )

            # Tag results with pattern descriptions
            for result in refined:
                # Combine pattern descriptions for why explanation
                all_pattern_descs = [initial_pattern.description] + [
                    p.description for p in refinement_patterns
                ]
                result["matched_patterns"] = all_pattern_descs

            all_refined_results.extend(refined)

        return all_refined_results

    def _pattern_matches(self, pattern: str, content: str) -> bool:
        """Check if a pattern matches content (regex or substring)."""
        import re

        # Try regex match first
        try:
            return bool(re.search(pattern, content, re.IGNORECASE))
        except re.error:
            # Fall back to simple substring match if regex invalid
            return pattern.lower() in content.lower()

    def _expand_context(self, file_path: str, line_num: int, lines_before: int = 3, lines_after: int = 5) -> str:
        """
        Expand context by reading lines before AND after the matched line.

        This helps capture association chains that might be split across lines:
        Example:
            Line 10: company.members
            Line 11:   .active        ← matched line
            Line 12:   .offset(...)
            Line 13:   .limit(...)
            Line 14:   .order(...)

        Args:
            file_path: Full path to the file
            line_num: Line number of the match (1-indexed)
            lines_before: Number of lines to read before the match
            lines_after: Number of lines to read after the match

        Returns:
            Expanded content with context (joined with single space for continuity)
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            # Calculate range (line_num is 1-indexed, list is 0-indexed)
            start_idx = max(0, line_num - lines_before - 1)
            end_idx = min(len(lines), line_num + lines_after)

            # Get context lines and join them
            context_lines = [line.strip() for line in lines[start_idx:end_idx]]

            # Join with space to create continuous code snippet
            expanded = ' '.join(context_lines)
            return expanded

        except Exception:
            # If we can't read the file, return empty
            return ""

    def _validate_and_score(
        self,
        results: List[Dict[str, Any]],
        sql_analysis: Any,
        rules: List[RailsSearchRule]
    ) -> List[SearchResult]:
        """
        Validate matches and calculate confidence scores using unified scoring system.

        Confidence based on:
        - WHERE clause completeness (strict semantic matching)
        - ORDER BY, LIMIT, OFFSET presence
        - Pattern distinctiveness
        """
        scored_results = []

        for result in results:
            content = result.get("content", "")
            matched_patterns = result.get("matched_patterns", [])

            # Expand context to capture association chains on previous AND following lines
            # NOTE: Limited expansion to avoid including unrelated control flow branches
            # (e.g., if/else branches that would incorrectly add conditions from other code paths)
            file_path = result.get("file", "")
            line_num = result.get("line", 0)
            if file_path and line_num > 0:
                # Try to get full file path for context expansion
                from pathlib import Path
                full_path = Path(self.project_root) / file_path if self.project_root else file_path
                # Reduced lines_after from 5 to 2 to avoid including else branches
                expanded_content = self._expand_context(str(full_path), line_num, lines_before=3, lines_after=2)

                # Use expanded content if available, otherwise use original
                if expanded_content:
                    content = expanded_content

            # 1. Perform strict WHERE clause matching
            sql_where_conditions = getattr(sql_analysis, "where_conditions", [])

            # Debug: Print content being analyzed
            if self.debug and "find_all_active" in content:
                print(f"\n🔍 DEBUG: Analyzing content for WHERE clause matching:")
                print(f"   File: {file_path}:{line_num}")
                print(f"   Content length: {len(content)}")
                print(f"   Content: {repr(content)}")

                # Also parse and show what we extract
                code_conditions = self.where_matcher.parser.parse_ruby_code(content)
                print(f"   Extracted {len(code_conditions)} WHERE conditions:")
                for cond in code_conditions:
                    print(f"     - {cond}")

            # Convert sql_analysis WHERE conditions to NormalizedCondition format
            from .where_clause_matcher import NormalizedCondition, Operator
            sql_normalized_conditions = []
            for cond in sql_where_conditions:
                # Handle IS NULL and IS NOT NULL operators
                if cond.operator.upper() == "IS_NULL":
                    operator = Operator.IS_NULL
                elif cond.operator.upper() == "IS_NOT_NULL":
                    operator = Operator.IS_NOT_NULL
                elif cond.operator.upper() == "IS":
                    # Legacy handling: Check if value indicates NULL or NOT NULL
                    operator = Operator.IS_NULL if cond.value is None else Operator.IS_NOT_NULL
                else:
                    operator = Operator.from_sqlglot(cond.operator)

                sql_normalized_conditions.append(NormalizedCondition(
                    column=cond.column.name.lower(),
                    operator=operator,
                    value=cond.value,
                    raw_pattern=f"{cond.column.name} {cond.operator} {cond.value}"
                ))

            # Parse WHERE conditions from code
            code_conditions = self.where_matcher.parser.parse_ruby_code(content)

            # Match conditions
            where_match_result = self.where_matcher.match(
                sql_normalized_conditions,
                code_conditions
            )

            # 2. Create clause presence object
            clause_presence = self.confidence_scorer.create_clause_presence(
                sql_analysis,
                content
            )

            # 3. Calculate pattern distinctiveness (based on number of matched patterns)
            # More patterns = higher distinctiveness
            pattern_distinctiveness = min(1.0, len(matched_patterns) * 0.25)

            # 4. Use unified scorer for final confidence
            scoring_result = self.confidence_scorer.score_match(
                where_match_result,
                clause_presence,
                pattern_distinctiveness,
                sql_analysis
            )

            final_confidence = scoring_result["confidence"]
            why = scoring_result["why"]

            # Add pattern match info to explanation
            if matched_patterns:
                why.insert(0, f"Matched {len(matched_patterns)} patterns: {', '.join(matched_patterns[:3])}")

            scored_results.append(SearchResult(
                file=result.get("file", ""),
                line=result.get("line", 0),
                content=content,
                matched_patterns=matched_patterns,
                confidence=final_confidence,
                why=why
            ))

        return scored_results

    def _get_merged_search_locations(
        self,
        rules: List[RailsSearchRule]
    ) -> List[SearchLocation]:
        """Get all search locations from rules, sorted by priority."""
        all_locations = []

        for rule in rules:
            locations = rule.get_search_locations()
            all_locations.extend(locations)

        # Deduplicate by glob pattern
        seen = set()
        unique_locations = []
        for loc in all_locations:
            if loc.glob_pattern not in seen:
                seen.add(loc.glob_pattern)
                unique_locations.append(loc)

        # Sort by priority
        unique_locations.sort(key=lambda loc: loc.priority)

        return unique_locations

    def _extract_file_extension(self, glob_pattern: str) -> str:
        """Extract file extension from glob pattern."""
        # app/models/**/*.rb → rb
        if "*.rb" in glob_pattern:
            return "rb"
        elif "*.erb" in glob_pattern:
            return "erb"
        else:
            return "rb"  # Default to Ruby

    def _try_semantic_matching(self, sql_analysis: Any) -> List[SearchPattern]:
        """
        Try to match SQL WHERE clauses to Rails scopes semantically.

        This is the NEW semantic matching approach that:
        1. Reads the model file
        2. Extracts all scope definitions
        3. Matches SQL WHERE clauses to scopes
        4. Returns high-priority search patterns based on matched scopes

        Returns:
            List of SearchPattern objects if semantic match found, empty list otherwise
        """
        # Check if we have a model name
        if not sql_analysis.primary_model:
            return []

        # Construct model file path
        # Convert plural table name to singular model file name (e.g., "members" -> "member.rb")
        model_name_singular = self._singularize_table_name(sql_analysis.primary_table.name)
        model_file = Path(self.project_root) / "app" / "models" / f"{model_name_singular}.rb"

        if not model_file.exists():
            if self.debug:
                print(f"   Model file not found: {model_file}")
            return []

        # Step 1: Extract scopes from model file
        analyzer = ModelScopeAnalyzer(debug=self.debug)
        scopes = analyzer.analyze_model(str(model_file))

        if not scopes:
            if self.debug:
                print(f"   No scopes found in model")
            return []

        # Step 2: Match SQL to scopes
        matcher = SQLToScopeMatcher(debug=self.debug)
        matches = matcher.find_matching_scopes(sql_analysis, scopes)

        if not matches:
            if self.debug:
                print(f"   No semantic scope matches")
            return []

        # Step 3: Use best match if confidence is high
        best_match = matches[0]
        if best_match.confidence < 0.8:
            if self.debug:
                print(f"   Best match '{best_match.name}' has low confidence ({best_match.confidence:.2f})")
            return []

        # Step 4: Generate search patterns based on matched scope
        patterns = []

        if self.debug:
            print(f"   Semantic match: {best_match.name} (confidence: {best_match.confidence:.2f})")

        # Primary pattern: Model.scope_name with LIMIT/OFFSET
        if getattr(sql_analysis, 'has_limit', False) or getattr(sql_analysis, 'has_offset', False):
            patterns.append(SearchPattern(
                pattern=rf"{sql_analysis.primary_model}\.{best_match.name}.*\.(?:limit|offset)\(",
                distinctiveness=0.95,  # Very high - semantic match
                description=f"{sql_analysis.primary_model}.{best_match.name} scope (semantic match)",
                clause_type="semantic_scope_match"
            ))

        # Fallback pattern: Just Model.scope_name
        patterns.append(SearchPattern(
            pattern=rf"{sql_analysis.primary_model}\.{best_match.name}\b",
            distinctiveness=0.9,  # High - semantic match
            description=f"{sql_analysis.primary_model}.{best_match.name} scope usage (semantic)",
            clause_type="semantic_scope_usage"
        ))

        return patterns

    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Deduplicate results by file:line, merging matched patterns."""
        seen = {}

        for result in results:
            key = f"{result.get('file', '')}:{result.get('line', 0)}"

            if key in seen:
                # Merge matched patterns
                existing = seen[key]
                existing["matched_patterns"] = list(set(
                    existing.get("matched_patterns", []) +
                    result.get("matched_patterns", [])
                ))
            else:
                seen[key] = result

        return list(seen.values())
