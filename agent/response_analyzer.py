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

    # Patterns that indicate concrete results
    CONCRETE_RESULT_PATTERNS = [
        r"app/.*\.rb:",           # File paths with line numbers
        r"def \w+",               # Method definitions
        r"class \w+",             # Class definitions
        r"scope :\w+",            # ActiveRecord scopes
        r"where\(",               # ActiveRecord where clauses
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

    def _has_rails_patterns(self, response: str) -> bool:
        """Check if response contains Rails-specific patterns."""
        rails_patterns = [
            "app/models/",
            "app/controllers/",
            "app/",
            ".rb:",
        ]
        return any(pattern in response for pattern in rails_patterns)

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

        Args:
            react_state: Current ReAct state

        Returns:
            True if high-quality results found, False otherwise
        """
        for step_info in react_state.step_results.values():
            if step_info.get('has_results', False):
                return True

            # Check for structured results in tool outputs
            tool_name = step_info.get('tool')
            tool_results = step_info.get('tool_results', {})

            if tool_name and tool_results:
                raw_result = tool_results.get(tool_name, '')
                if self._analyze_structured_result(raw_result, tool_name):
                    return True

        return False

    def _analyze_structured_result(self, result: str, tool_name: str) -> bool:
        """Analyze structured tool results for quality indicators."""
        try:
            if isinstance(result, str):
                parsed = json.loads(result)
            else:
                parsed = result

            if isinstance(parsed, dict):
                return self._check_tool_specific_results(parsed, tool_name)

        except (json.JSONDecodeError, TypeError):
            # Fallback to text-based analysis
            return self._has_concrete_results(str(result))

        return False

    def _check_tool_specific_results(self, parsed: Dict[str, Any], tool_name: str) -> bool:
        """Check tool-specific result structures for quality."""
        if tool_name == 'enhanced_sql_rails_search':
            matches = parsed.get('matches', [])
            return isinstance(matches, list) and len(matches) > 0


        elif tool_name == 'ripgrep':
            matches = parsed.get('matches', [])
            return isinstance(matches, list) and len(matches) > 0

        elif tool_name in ['model_analyzer', 'controller_analyzer']:
            # Check for meaningful analysis results
            return bool(parsed.get('analysis')) or bool(parsed.get('methods'))

        elif tool_name == 'ast_grep':
            matches = parsed.get('matches', [])
            return isinstance(matches, list) and len(matches) > 0

        # Default: assume any structured response is meaningful
        return len(parsed) > 0

    def should_force_different_tool(self, react_state: ReActState,
                                   step: int, repetition_limit: int = 3) -> bool:
        """
        Determine if we should force using a different tool.

        Args:
            react_state: Current ReAct state
            step: Current step number
            repetition_limit: Maximum repetitions before forcing change

        Returns:
            True if should force different tool, False otherwise
        """
        # Only force different tool if we've used the same tool too many times AND no results found
        for tool_name, stats in react_state.tool_stats.items():
            if stats.usage_count >= repetition_limit:
                # Check if we actually found high-quality results - don't force if we have good results
                if not react_state.has_high_quality_results():
                    logger.info(f"Tool {tool_name} used {stats.usage_count} times without results, forcing change")
                    return True
                else:
                    logger.info(f"Tool {tool_name} used {stats.usage_count} times but found results, continuing")

        # Force if we're stuck in a loop (but only if no results found)
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
            "ctags": [
                "Using ctags",
                "⚙ Using ctags"
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