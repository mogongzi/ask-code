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

        # Step 1: Get applicable domain rules
        applicable_rules = self.rule_set.get_applicable_rules(sql_analysis)
        if self.debug:
            print(f"   Applicable rules: {[type(r).__name__ for r in applicable_rules]}")

        # Step 2: Build and rank all search patterns
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

        # Sort by distinctiveness (rare → common)
        all_patterns.sort(key=lambda p: p.distinctiveness, reverse=True)

        return all_patterns

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

        # Extract filter pattern strings
        filter_pattern_strings = [p.pattern for p in refinement_patterns]

        if self.debug:
            print(f"         Using file-level filtering with {len(refinement_patterns)} complementary patterns:")
            for p in refinement_patterns:
                print(f"            - {p.description} (type: {p.clause_type})")

        # Execute file-level search for each location
        all_refined_results = []

        for location in search_locations:
            file_ext = self._extract_file_extension(location.glob_pattern)

            # Use the new file-level filter method from CodeSearchEngine
            refined = self.search_engine.search_file_level_filter(
                initial_pattern.pattern,
                filter_pattern_strings,
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

    def _validate_and_score(
        self,
        results: List[Dict[str, Any]],
        sql_analysis: Any,
        rules: List[RailsSearchRule]
    ) -> List[SearchResult]:
        """
        Validate matches and calculate confidence scores.

        Confidence based on:
        - Number of matched patterns (more = higher)
        - Rule-specific validation scores
        - Completeness (all SQL clauses accounted for)
        """
        scored_results = []

        for result in results:
            # Calculate base confidence from matched patterns
            matched_patterns = result.get("matched_patterns", [])
            base_confidence = min(1.0, len(matched_patterns) * 0.25)

            # Get rule-specific validation scores
            rule_confidences = []
            for rule in rules:
                rule_score = rule.validate_match(result, sql_analysis)
                rule_confidences.append(rule_score)

            # Average rule confidence
            avg_rule_confidence = sum(rule_confidences) / len(rule_confidences) if rule_confidences else 0.5

            # Final confidence is weighted average
            final_confidence = (base_confidence * 0.4) + (avg_rule_confidence * 0.6)

            # Build "why" explanation
            why = [
                f"Matched {len(matched_patterns)} patterns: {', '.join(matched_patterns[:3])}"
            ]

            # Add completeness check
            completeness = self._check_completeness(result, sql_analysis)
            if completeness["missing"]:
                why.append(f"Missing: {', '.join(completeness['missing'])}")
                final_confidence *= 0.8  # Reduce confidence if incomplete
            else:
                why.append("All SQL clauses accounted for")
                final_confidence = min(1.0, final_confidence * 1.2)  # Boost confidence

            scored_results.append(SearchResult(
                file=result.get("file", ""),
                line=result.get("line", 0),
                content=result.get("content", ""),
                matched_patterns=matched_patterns,
                confidence=final_confidence,
                why=why
            ))

        return scored_results

    def _check_completeness(
        self,
        result: Dict[str, Any],
        sql_analysis: Any
    ) -> Dict[str, Any]:
        """
        Check if the match accounts for all SQL clauses.

        Returns:
            {
                "complete": True/False,
                "missing": ["LIMIT", "ORDER BY", ...]
            }
        """
        content = result.get("content", "").lower()
        missing = []

        # Check LIMIT
        if getattr(sql_analysis, "has_limit", False):
            if ".limit(" not in content and ".take(" not in content:
                missing.append("LIMIT")

        # Check OFFSET
        if "offset" in sql_analysis.raw_sql.lower():
            if ".offset(" not in content:
                missing.append("OFFSET")

        # Check ORDER BY
        if getattr(sql_analysis, "has_order", False):
            if ".order(" not in content:
                missing.append("ORDER BY")

        # Check WHERE conditions (at least some should be present)
        where_conditions = getattr(sql_analysis, "where_conditions", [])
        if where_conditions:
            matched_conditions = sum(
                1 for cond in where_conditions
                if cond.column.name.lower() in content
            )
            if matched_conditions == 0:
                missing.append("WHERE conditions")

        return {
            "complete": len(missing) == 0,
            "missing": missing
        }

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
