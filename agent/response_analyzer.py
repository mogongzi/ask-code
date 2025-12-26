"""
Response analyzer for determining ReAct step outcomes.

SIMPLIFIED VERSION: Trusts the LLM to decide when it's done.
Instead of parsing LLM output with regex patterns, we use a simple rule:
- If LLM stops calling tools and provides substantive text, it's done.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Set
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
    """
    Simplified response analyzer that trusts LLM judgment.

    Core principle: If the LLM stops calling tools and provides
    a substantive response, accept it as the final answer.
    """

    # Minimum response length to be considered "substantive"
    MIN_SUBSTANTIVE_LENGTH = 200

    def __init__(self):
        """Initialize the response analyzer."""
        pass

    def analyze_response(
        self,
        response: str,
        react_state: ReActState,
        step: int,
        planning_tool: Any = None  # Kept for API compatibility, but ignored
    ) -> AnalysisResult:
        """
        Analyze an LLM response to determine if it's final.

        Simple logic:
        - If LLM stopped calling tools AND provided substantive text → done
        - Otherwise → continue

        Args:
            response: The LLM response text
            react_state: Current ReAct state
            step: Current step number
            planning_tool: Ignored (kept for API compatibility)

        Returns:
            AnalysisResult with analysis outcome
        """
        # LLM is done if: no tool calls AND substantive text
        if (react_state.consecutive_no_tool_calls >= 1 and
            len(response) > self.MIN_SUBSTANTIVE_LENGTH):
            logger.debug(f"Step {step}: LLM provided substantive answer ({len(response)} chars) without tools")
            return AnalysisResult(
                is_final=True,
                confidence="high",
                reason="LLM provided substantive answer without calling tools",
                suggestions=[],
                has_concrete_results=True
            )

        # Continue - LLM is still working
        return AnalysisResult(
            is_final=False,
            confidence="low",
            reason="Waiting for LLM to complete analysis",
            suggestions=[],
            has_concrete_results=False
        )

    def has_high_quality_tool_results(self, react_state: ReActState) -> bool:
        """
        Check if any tool results contain high-quality matches.

        Kept for observability/logging, but NOT used for control flow.
        """
        return react_state.has_high_quality_results()

    def should_force_different_tool(
        self,
        react_state: ReActState,
        step: int,
        repetition_limit: int = 3
    ) -> bool:
        """
        Detect exact infinite loops only.

        Only returns True if the EXACT same tool with EXACT same input
        has been called 3+ times in a row.

        Args:
            react_state: Current ReAct state
            step: Current step number
            repetition_limit: Threshold for exact repetitions

        Returns:
            True only if stuck in exact infinite loop
        """
        # Check for exact repetition pattern
        if len(react_state.search_attempts) >= repetition_limit:
            recent = react_state.search_attempts[-repetition_limit:]
            if len(set(recent)) == 1:  # All identical
                logger.warning(f"Exact infinite loop detected: {recent[0]} repeated {repetition_limit}x")
                return True

        return False

    def generate_finalization_prompt(self) -> str:
        """Generate a prompt to request final answer synthesis."""
        return (
            "Please provide your final answer based on what you've found. "
            "Include the file path, line numbers, and relevant code snippets."
        )

    def generate_tool_constraint_prompt(
        self,
        react_state: ReActState,
        available_tools: Set[str]
    ) -> str:
        """
        Generate a constraint prompt for stuck loops.

        Only used when exact infinite loop is detected.
        """
        tools_used = list(react_state.tools_used)
        unused_tools = react_state.get_unused_tools(available_tools)

        prompt = "\n⚠️ You seem to be repeating the same action. "
        prompt += "Try a different approach or provide your answer with what you've found.\n"

        if unused_tools:
            prompt += f"Available tools you haven't tried: {', '.join(unused_tools)}\n"

        return prompt
