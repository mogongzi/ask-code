"""
Response analyzer for determining ReAct step outcomes.

This module provides analysis capabilities for LLM responses,
determining when to stop, continue, or change strategies.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass

from agent.state_machine import ReActState


logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of response analysis."""
    is_final: bool
    confidence: str
    reason: str
    suggestions: List[str]
    has_concrete_results: bool


class ResponseAnalyzer:
    """Analyzes LLM responses to determine ReAct flow control."""

    # Indicators that suggest a final answer
    FINAL_ANSWER_INDICATORS = [
        "I found the source code at",
        "The exact code that generates this SQL is",
        "Located the Rails code in",
        "Here is the specific Rails method",
        "Found the Rails source:",
        "## Final Answer",
        "## Conclusion"
    ]

    # Phrases that indicate intent to investigate further (NOT final)
    INVESTIGATION_INTENT_PATTERNS = [
        r"let me (examine|check|read|analyze|look at|investigate)",
        r"I'll (examine|check|read|analyze|look at|investigate)",
        r"I will (examine|check|read|analyze|look at|investigate)",
        r"let's (examine|check|read|analyze|look at|investigate)",
        r"going to (examine|check|read|analyze|look at|investigate)",
        r"need to (examine|check|read|analyze|look at|investigate)",
        r"should (examine|check|read|analyze|look at|investigate)",
        r"which was identified as",  # "...file which was identified as the main source"
        r"identified as the (main|primary) source",
    ]

    # Patterns that indicate concrete results
    CONCRETE_RESULT_PATTERNS = [
        r"(app|lib|config)/[\w/]+\.rb",  # Ruby files in Rails directories (with or without colon)
        r"def \w+",                       # Method definitions
        r"class \w+",                     # Class definitions
        r"scope :\w+",                    # ActiveRecord scopes
        r"where\(",                       # ActiveRecord where clauses
    ]

    # Rails directory patterns (expanded to include lib/, config/, etc.)
    RAILS_DIRECTORIES = [
        "app/models/",
        "app/controllers/",
        "app/services/",
        "app/helpers/",
        "app/jobs/",
        "app/mailers/",
        "app/",
        "lib/",
        "config/",
    ]

    def __init__(self):
        """Initialize the response analyzer."""
        pass

    def analyze_response(self, response: str, react_state: ReActState,
                        step: int) -> AnalysisResult:
        """
        Analyze an LLM response to determine if it's final or needs continuation.

        Args:
            response: The LLM response text
            react_state: Current ReAct state
            step: Current step number

        Returns:
            AnalysisResult with analysis outcome
        """
        response_lower = response.lower()

        # CRITICAL: Check for investigation intent first (overrides other patterns)
        # If the LLM says "let me examine/check/analyze", it's NOT final
        for pattern in self.INVESTIGATION_INTENT_PATTERNS:
            if re.search(pattern, response_lower, re.IGNORECASE):
                return AnalysisResult(
                    is_final=False,
                    confidence="high",
                    reason=f"Response indicates intent to investigate further",
                    suggestions=["Wait for next tool execution"],
                    has_concrete_results=False
                )

        # Check for explicit final answer indicators
        for indicator in self.FINAL_ANSWER_INDICATORS:
            if indicator.lower() in response_lower:
                return AnalysisResult(
                    is_final=True,
                    confidence="high",
                    reason=f"Contains final answer indicator: '{indicator}'",
                    suggestions=[],
                    has_concrete_results=True
                )

        # Check for semantic final answer patterns (emoji-prefixed conclusions, etc.)
        semantic_result = self._check_semantic_final_patterns(response, react_state)
        if semantic_result:
            return semantic_result

        # Check for concrete code results with file paths
        has_concrete = self._has_concrete_results(response)
        if has_concrete and self._has_rails_patterns(response):
            return AnalysisResult(
                is_final=True,
                confidence="high",
                reason="Contains concrete Rails code with file locations",
                suggestions=[],
                has_concrete_results=True
            )

        # Check for specific Rails ActiveRecord patterns
        if self._has_activerecord_patterns(response):
            return AnalysisResult(
                is_final=True,
                confidence="medium",
                reason="Contains specific ActiveRecord code patterns",
                suggestions=[],
                has_concrete_results=True
            )

        # Context-aware detection: if no tool calls after having concrete results, likely final
        if self._is_likely_final_from_context(response, react_state):
            return AnalysisResult(
                is_final=True,
                confidence="medium",
                reason="Concrete results presented without new tool calls (likely finalization)",
                suggestions=[],
                has_concrete_results=has_concrete
            )

        # Check if we should continue based on step and state
        continue_reason, suggestions = self._should_continue_analysis(
            response, react_state, step
        )

        return AnalysisResult(
            is_final=False,
            confidence="low",
            reason=continue_reason,
            suggestions=suggestions,
            has_concrete_results=has_concrete
        )

    def _has_concrete_results(self, response: str) -> bool:
        """Check if response contains concrete file paths or code snippets."""
        for pattern in self.CONCRETE_RESULT_PATTERNS:
            if re.search(pattern, response):
                return True
        return ("app/" in response and ".rb" in response) or ("def " in response)

    def _has_callbacks_needing_investigation(self, response: str, react_state: ReActState) -> bool:
        """
        Check if response mentions callbacks that haven't been investigated yet.

        IMPORTANT: Only returns True for the FIRST time callbacks are detected.
        After 2-3 file_reader calls, assumes sufficient investigation has occurred.

        Args:
            response: The LLM response text
            react_state: Current ReAct state

        Returns:
            True if callbacks are mentioned but not fully investigated (and investigation not exhausted)
        """
        # OPTIMIZATION 1: If we've used file_reader 3+ times, stop investigating callbacks
        file_reader_count = react_state.tool_stats.get('file_reader', None)
        if file_reader_count and file_reader_count.usage_count >= 3:
            return False  # Already investigated enough

        # OPTIMIZATION 2: If we're past step 10, stop investigating (allow finalization)
        # This allows more time for complex transaction analysis but still forces synthesis
        if react_state.current_step >= 10:
            return False

        # Check for callback mentions
        callback_patterns = [
            r'after_save\s*:\s*\w+',
            r'after_create\s*:\s*\w+',
            r'before_save\s*:\s*\w+',
            r'after_commit\s*:\s*\w+',
            r'callback[s]?\s+(fire|trigger|execute)',
        ]

        has_callback_mention = any(
            re.search(pattern, response, re.IGNORECASE)
            for pattern in callback_patterns
        )

        if not has_callback_mention:
            return False

        # Check if we've read callback implementations
        has_transaction = 'transaction' in response.lower() or 'BEGIN' in response
        has_multiple_queries = response.count('INSERT') + response.count('UPDATE') + response.count('SELECT') > 3

        # If transaction with callbacks but no implementation details, needs investigation
        if has_transaction and has_callback_mention and has_multiple_queries:
            # Check if we've already read ANY callback implementations (def method_name patterns)
            has_def_patterns = response.count('def ') >= 2  # At least 2 method definitions shown
            has_file_reads = file_reader_count and file_reader_count.usage_count >= 1

            # If we've read files and seen method definitions, consider it investigated
            if has_file_reads and has_def_patterns:
                return False

            # Only suggest investigation if we haven't started yet
            return not has_file_reads

        return False

    def _has_incomplete_sql_match(self, response: str, react_state: ReActState) -> bool:
        """
        Detect when agent found partial SQL matches but is claiming high confidence.

        Warning signs:
        - Mentions "missing" clauses but still claims match
        - Shows "partial" confidence from tool output
        - Very few tool calls (< 2) for complex SQL queries
        - Tool output shows low match scores or missing conditions

        Args:
            response: The LLM response text
            react_state: Current ReAct state

        Returns:
            True if incomplete SQL match detected and needs more investigation
        """
        # Only check in early steps - after step 6, allow finalization
        if react_state.current_step > 6:
            return False

        # Check if this is an SQL search query (look for SQL patterns in recent steps)
        if not hasattr(react_state, 'steps') or not react_state.steps:
            return False  # No steps yet or not a ReActState with steps

        # Get tool names from recent steps (ReActStep objects, not dicts)
        recent_tool_uses = [
            step.tool_name for step in react_state.steps[-3:]
            if hasattr(step, 'tool_name') and step.tool_name
        ]
        is_sql_search = 'enhanced_sql_rails_search' in recent_tool_uses

        if not is_sql_search:
            return False  # Not an SQL search task

        # Detection patterns for incomplete matches
        incomplete_indicators = [
            # Explicit mentions of missing elements
            (r'missing[:：]?\s*(WHERE|condition|ORDER|LIMIT|OFFSET|custom\w+)', 'missing clauses'),
            (r'but missing', 'incomplete match'),
            (r'without.*(?:ORDER|LIMIT|OFFSET)', 'missing clauses'),

            # Partial confidence indicators
            (r'confidence["\']?\s*:\s*["\']?(partial|low)', 'low confidence'),
            (r'score["\']?\s*:\s*0\.[0-6]', 'low match score'),

            # Condition mismatch indicators
            (r'matched\s+\d+/\d+\s+conditions', 'partial condition match'),
            (r'\d+\s+WHERE\s+condition\(s\)', 'missing conditions'),

            # Agent acknowledging incomplete match
            (r'(?:partial|incomplete)\s+match', 'incomplete'),
            (r'only\s+(?:matches|found)\s+(?:some|part)', 'partial'),
        ]

        found_indicators = []
        for pattern, label in incomplete_indicators:
            if re.search(pattern, response, re.IGNORECASE):
                found_indicators.append(label)

        # If we found indicators AND very few tool calls, needs more investigation
        if found_indicators:
            tool_count = react_state.current_step
            if tool_count < 3:
                # Incomplete match detected, needs more investigation
                return True

        # Check for "EXACT MATCH" claims with missing indicators
        # This is the dangerous case - agent claiming exactness despite missing pieces
        has_exact_claim = bool(re.search(r'EXACT\s+MATCH|match.*exactly', response, re.IGNORECASE))
        if has_exact_claim and found_indicators:
            # False exact match claim detected
            return True

        return False

    def _check_semantic_final_patterns(self, response: str, react_state: ReActState) -> Optional[AnalysisResult]:
        """
        Check for semantic patterns that indicate a final answer.

        This detects conclusions that may not use exact hardcoded phrases,
        such as emoji-prefixed headings, conclusion structures, etc.

        Args:
            response: The LLM response text
            react_state: Current ReAct state

        Returns:
            AnalysisResult if final answer detected, None otherwise
        """
        # Pattern 1: Structured conclusion sections with headers
        # Look for markdown headers or explicit conclusion keywords
        conclusion_headers = [
            r'(^|\n)#{1,3}\s*(EXACT MATCH|FOUND|CONCLUSION|FINAL ANSWER|ANALYSIS COMPLETE)',
            r'(^|\n)(EXACT MATCH|FOUND|SOLUTION)[:：]',
        ]

        for header_pattern in conclusion_headers:
            if re.search(header_pattern, response, re.IGNORECASE | re.MULTILINE):
                if self._has_concrete_results(response) and self._has_rails_patterns(response):
                    return AnalysisResult(
                        is_final=True,
                        confidence="high",
                        reason="Contains structured conclusion section with file locations",
                        suggestions=[],
                        has_concrete_results=True
                    )

        # Pattern 2: File location format (indicates found source code)
        # Look for explicit file location patterns: "File: path" or "Location: path" followed by code
        file_location_patterns = [
            r'(^|\n)(File|Location|Source):\s+[\w/]+\.rb',
            r'(^|\n)[\w/]+\.rb:\d+',  # file.rb:123 format
        ]

        for location_pattern in file_location_patterns:
            if re.search(location_pattern, response, re.IGNORECASE | re.MULTILINE):
                # Must also have code context (line numbers, code snippets)
                has_line_ref = bool(re.search(r'(Line|line):\s*\d+', response))
                has_code_snippet = bool(re.search(r'(Code|code):', response))

                if (has_line_ref or has_code_snippet) and self._has_rails_patterns(response):
                    return AnalysisResult(
                        is_final=True,
                        confidence="high",
                        reason="Contains explicit file location with code context",
                        suggestions=[],
                        has_concrete_results=True
                    )

        # Pattern 3: Confidence statements + execution flow (comprehensive answer structure)
        has_confidence = bool(re.search(r'confidence|likely|certain|match', response, re.IGNORECASE))
        has_flow = bool(re.search(r'(execution flow|flow:|step \d+|triggered by)', response, re.IGNORECASE))
        has_code = self._has_concrete_results(response)
        has_rails = self._has_rails_patterns(response)

        if has_confidence and has_flow and has_code and has_rails and len(response) > 500:
            return AnalysisResult(
                is_final=True,
                confidence="high",
                reason="Contains comprehensive answer with confidence, flow analysis, and code locations",
                suggestions=[],
                has_concrete_results=True
            )

        # Pattern 4: If we're past step 12 and have concrete results, force finalization
        # This prevents the agent from endlessly searching when it already has good findings
        if react_state.current_step >= 12 and has_code and has_rails and len(response) > 300:
            return AnalysisResult(
                is_final=True,
                confidence="medium",
                reason=f"Step {react_state.current_step}: Has concrete code results, time to synthesize findings",
                suggestions=[],
                has_concrete_results=True
            )

        # Pattern 5: Check for incomplete SQL matches (partial matches claiming high confidence)
        # This prevents premature finalization when search found partial matches only
        if self._has_incomplete_sql_match(response, react_state):
            return AnalysisResult(
                is_final=False,
                confidence="low",
                reason="Partial SQL match found - missing conditions or clauses",
                suggestions=[
                    "Search for missing SQL conditions (e.g., specific column names)",
                    "Use file_reader to examine candidate files in detail",
                    "Look for scope definitions or dynamic query builders"
                ],
                has_concrete_results=True
            )

        # Pattern 6: Check if callbacks need investigation (ONLY if no concrete answer found above)
        # This check runs LAST to avoid blocking finalization when we have complete answers
        if self._has_callbacks_needing_investigation(response, react_state):
            return AnalysisResult(
                is_final=False,
                confidence="medium",
                reason="Response mentions callbacks but implementations not yet investigated",
                suggestions=["Read callback implementations for complete understanding"],
                has_concrete_results=True
            )

        return None

    def _is_likely_final_from_context(self, response: str, react_state: ReActState) -> bool:
        """
        Use step context to determine if this is likely a final answer.

        This detects cases where:
        - Previous step(s) had tool calls
        - Current step has no tool calls (presenting results)
        - Response contains concrete results

        Args:
            response: The LLM response text
            react_state: Current ReAct state

        Returns:
            True if likely final based on context, False otherwise
        """
        # Check if we just stopped using tools (consecutive_no_tool_calls == 1)
        # and we have concrete results to present
        if react_state.consecutive_no_tool_calls == 1:
            has_concrete = self._has_concrete_results(response)
            has_rails = self._has_rails_patterns(response)
            is_substantial = len(response) > 300  # Non-trivial response

            # If we have concrete results and stopped calling tools, likely final
            if has_concrete and has_rails and is_substantial:
                return True

        return False

    def _has_rails_patterns(self, response: str) -> bool:
        """Check if response contains Rails-specific patterns."""
        # Check for any Rails directory path
        for directory in self.RAILS_DIRECTORIES:
            if directory in response:
                return True

        # Also accept Ruby files without explicit directory if they have .rb extension
        if re.search(r'\.rb\b', response):
            return True

        return False

    def _has_activerecord_patterns(self, response: str) -> bool:
        """Check for specific ActiveRecord code patterns."""
        ar_patterns = [
            r"Model\.exists\?",
            r"Model\.where\(",
            r"Model\.find_by",
            r"scope :\w+",
            r"belongs_to :\w+",
            r"has_many :\w+",
            r"validates :\w+",
        ]

        for pattern in ar_patterns:
            if re.search(pattern, response, re.IGNORECASE):
                return True

        # Check for model/controller file paths with method definitions
        return (
            ("app/models/" in response or "app/controllers/" in response) and
            ("def " in response or "scope " in response or "where(" in response)
        )

    def _should_continue_analysis(self, response: str, react_state: ReActState,
                                 step: int) -> tuple[str, List[str]]:
        """Determine if analysis should continue and provide suggestions."""
        suggestions = []

        # If no tools have been used yet, suggest starting
        if not react_state.tools_used:
            return (
                "No tools used yet, should start analysis",
                ["Use enhanced_sql_rails_search for SQL queries",
                 "Use ripgrep for general code search"]
            )

        # If only one tool has been used multiple times, suggest variety
        if len(react_state.tools_used) == 1 and step > 2:
            used_tool = list(react_state.tools_used)[0]
            return (
                f"Only {used_tool} used, need different approach",
                [
                    "Try model_analyzer for model-specific analysis",
                    "Use controller_analyzer for controller patterns",
                    "Try ast_grep for structural code search"
                ]
            )

        # If we have some results but not definitive, suggest refinement
        if react_state.has_high_quality_results():
            return (
                "Has partial results, may need refinement or synthesis",
                ["Synthesize findings into final answer",
                 "Search for additional context"]
            )

        # Default: continue with next logical step
        return (
            "Need more information to provide definitive answer",
            ["Try different search strategy",
             "Look for related patterns"]
        )

    def has_high_quality_tool_results(self, react_state: ReActState) -> bool:
        """
        Check if any tool results contain high-quality matches.

        Delegates to ReActState for centralized quality checking.

        Args:
            react_state: Current ReAct state

        Returns:
            True if high-quality results found, False otherwise
        """
        return react_state.has_high_quality_results()

    def should_force_different_tool(self, react_state: ReActState,
                                   step: int, repetition_limit: int = 3) -> bool:
        """
        Determine if we should force using a different tool.

        Delegates to ReActState for centralized tool forcing logic with
        additional repetition limit check.

        Args:
            react_state: Current ReAct state
            step: Current step number
            repetition_limit: Maximum repetitions before forcing change

        Returns:
            True if should force different tool, False otherwise
        """
        # Check if any single tool exceeded the repetition limit
        for tool_name, stats in react_state.tool_stats.items():
            if stats.usage_count >= repetition_limit:
                # Check if we actually found high-quality results
                if not react_state.has_high_quality_results():
                    logger.info(f"Tool {tool_name} used {stats.usage_count} times without results, forcing change")
                    return True
                else:
                    logger.info(f"Tool {tool_name} used {stats.usage_count} times but found results, continuing")

        # Delegate to state machine for pattern-based detection
        if react_state.should_force_different_tool(step_threshold=2):
            logger.info("Detected tool usage loop, forcing change")
            return True

        return False

    def generate_finalization_prompt(self) -> str:
        """Generate a prompt to request final answer synthesis."""
        return (
            "Please synthesize the final answer based on the tool results above. "
            "List the exact Rails code locations that generate the SQL, including file path and line numbers, "
            "and include a one‑line code snippet for each. Provide a brief explanation of why they match. "
            "Keep it concise and specific."
        )

    def generate_tool_constraint_prompt(self, react_state: ReActState,
                                      available_tools: Set[str]) -> str:
        """
        Generate a constraint prompt that forces different tool usage.

        Args:
            react_state: Current ReAct state
            available_tools: Set of available tool names

        Returns:
            Constraint prompt string
        """
        tools_used = list(react_state.tools_used)
        unused_tools = react_state.get_unused_tools(available_tools)

        # Check if we actually found results to make the message accurate
        has_results = react_state.has_high_quality_results()

        if has_results:
            prompt = f"\n⚠️ The tool {tools_used} found some results, but let's verify with another approach.\n"
        else:
            prompt = f"\n⚠️ CONSTRAINT: Tool {tools_used} didn't find sufficient results.\n"

        prompt += f"🚫 FORBIDDEN: Do NOT use these tools again: {', '.join(tools_used)}\n"
        prompt += f"✅ REQUIRED: You MUST use one of these unused tools: {', '.join(unused_tools)}\n"
        prompt += "Choose the most appropriate tool from the unused list and explain your reasoning.\n"

        return prompt

    def extract_tool_used(self, response: str) -> Optional[str]:
        """
        Extract which tool was used from the response text.

        Args:
            response: LLM response text

        Returns:
            Tool name if found, None otherwise
        """
        tool_patterns = {
            "enhanced_sql_rails_search": [
                "Using enhanced_sql_rails_search",
                "⚙ Using enhanced_sql_rails_search"
            ],
            "ripgrep": [
                "Using ripgrep",
                "⚙ Using ripgrep"
            ],
            "ast_grep": [
                "Using ast_grep",
                "⚙ Using ast_grep"
            ],
            "model_analyzer": [
                "Using model_analyzer",
                "⚙ Using model_analyzer"
            ],
            "controller_analyzer": [
                "Using controller_analyzer",
                "⚙ Using controller_analyzer"
            ]
        }

        for tool, patterns in tool_patterns.items():
            for pattern in patterns:
                if pattern in response:
                    return tool

        return None
