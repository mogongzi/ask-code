"""
ReAct state machine for managing reasoning and acting loop state.

This module provides centralized state management for the ReAct pattern,
tracking steps, tool usage, and decision making.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum


logger = logging.getLogger(__name__)


class StepType(Enum):
    """Types of ReAct steps."""

    THOUGHT = "thought"
    ACTION = "action"
    OBSERVATION = "observation"
    ANSWER = "answer"


@dataclass
class ReActStep:
    """Represents a single step in the ReAct loop."""

    step_type: StepType
    content: str
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[Any] = None
    step_number: int = 0
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary representation."""
        return {
            "step_type": self.step_type.value,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "tool_output": str(self.tool_output) if self.tool_output else None,
            "step_number": self.step_number,
            "timestamp": self.timestamp,
        }


@dataclass
class ToolUsageStats:
    """Statistics for tool usage during ReAct session."""

    name: str
    usage_count: int = 0
    last_used_step: int = 0
    success_count: int = 0
    error_count: int = 0


@dataclass
class ReActState:
    """State container for ReAct reasoning loop."""

    # Core tracking
    current_step: int = 0
    steps: List[ReActStep] = field(default_factory=list)

    # Tool usage tracking
    tools_used: Set[str] = field(default_factory=set)
    tool_stats: Dict[str, ToolUsageStats] = field(default_factory=dict)
    search_attempts: List[str] = field(default_factory=list)

    # Results tracking
    step_results: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)

    # Control flags
    finalize_requested: bool = False
    finalize_requested_at_step: Optional[int] = None
    should_stop: bool = False
    stop_reason: Optional[str] = None

    # Stuck detection
    consecutive_no_tool_calls: int = 0
    last_step_had_tool_calls: bool = False

    def add_step(self, step: ReActStep) -> None:
        """Add a new step to the state."""
        step.step_number = len(self.steps) + 1
        self.steps.append(step)
        self.current_step = step.step_number
        logger.debug(f"Added step {step.step_number}: {step.step_type.value}")

    def record_tool_usage(self, tool_name: str, success: bool = True) -> None:
        """Record tool usage statistics."""
        self.tools_used.add(tool_name)

        if tool_name not in self.tool_stats:
            self.tool_stats[tool_name] = ToolUsageStats(name=tool_name)

        stats = self.tool_stats[tool_name]
        stats.usage_count += 1
        stats.last_used_step = self.current_step

        if success:
            stats.success_count += 1
        else:
            stats.error_count += 1

        # Track search attempts
        attempt = f"Step {self.current_step}: Used {tool_name}"
        self.search_attempts.append(attempt)
        logger.debug(f"Recorded tool usage: {tool_name} (success: {success})")

    def record_step_result(
        self,
        step_num: int,
        tool_name: str,
        response: str,
        tool_results: Dict[str, str],
        has_results: bool = False,
    ) -> None:
        """Record results from a step."""
        self.step_results[step_num] = {
            "tool": tool_name,
            "response": response,
            "tool_results": tool_results,
            "has_results": has_results,
            "timestamp": self.current_step,
        }
        logger.debug(f"Recorded results for step {step_num}")

    def get_tool_usage_count(self, tool_name: str) -> int:
        """Get usage count for a specific tool."""
        return self.tool_stats.get(tool_name, ToolUsageStats(tool_name)).usage_count

    def has_tool_repetition(self, tool_name: str, limit: int) -> bool:
        """Check if a tool has been used too many times."""
        return self.get_tool_usage_count(tool_name) >= limit

    def get_unused_tools(self, available_tools: Set[str]) -> List[str]:
        """Get list of available tools that haven't been used."""
        unused = sorted(available_tools - self.tools_used)
        return unused

    def should_force_different_tool(self, step_threshold: int = 2) -> bool:
        """Determine if we should force using a different tool."""
        # Only force different tool if:
        # 1. The same tool was used multiple times (not just once!)
        # 2. AND no high-quality results were found
        if (
            len(self.tools_used) == 1 and self.current_step > step_threshold + 1
        ):  # Allow more attempts
            # Check if we actually found results - don't force if we have good results
            if not self.has_high_quality_results():
                return True

        # Force if we're stuck in a loop (last two attempts were the same)
        if len(self.search_attempts) >= 2:
            recent_attempts = self.search_attempts[-2:]
            if recent_attempts[0] == recent_attempts[1]:
                return True

        return False

    def has_high_quality_results(self) -> bool:
        """Check if any step has produced high-quality results."""
        for step_info in self.step_results.values():
            if step_info.get("has_results", False):
                return True

            # Check for structured tool results
            tool_name = step_info.get("tool")
            tool_results = step_info.get("tool_results", {})

            if tool_name and tool_results:
                raw_result = tool_results.get(tool_name, "")
                if self._has_structured_matches(raw_result, tool_name):
                    return True

        return False

    def _has_structured_matches(self, result: str, tool_name: str) -> bool:
        """Check if a tool result contains structured matches."""
        try:
            import json

            parsed = json.loads(result) if isinstance(result, str) else result

            if isinstance(parsed, dict):
                if tool_name == "enhanced_sql_rails_search":
                    matches = parsed.get("matches", [])
                    return isinstance(matches, list) and len(matches) > 0
                elif tool_name == "ripgrep":
                    matches = parsed.get("matches", [])
                    return isinstance(matches, list) and len(matches) > 0
        except (json.JSONDecodeError, TypeError):
            pass

        return False

    def request_finalization(self) -> None:
        """Request finalization of the ReAct loop."""
        self.finalize_requested = True
        self.finalize_requested_at_step = self.current_step
        logger.debug(f"Finalization requested at step {self.current_step}")

    def stop_with_reason(self, reason: str) -> None:
        """Stop the ReAct loop with a specific reason."""
        self.should_stop = True
        self.stop_reason = reason
        logger.info(f"ReAct loop stopped: {reason}")

    def is_stuck_after_finalization(
        self, max_steps_after_finalization: int = 2
    ) -> bool:
        """Check if agent is stuck after finalization was requested."""
        if not self.finalize_requested or self.finalize_requested_at_step is None:
            return False

        steps_since_finalization = self.current_step - self.finalize_requested_at_step
        return steps_since_finalization >= max_steps_after_finalization

    def record_tool_call_status(self, has_tool_calls: bool) -> None:
        """Track whether the current step had tool calls for stuck detection."""
        if has_tool_calls:
            self.consecutive_no_tool_calls = 0
            self.last_step_had_tool_calls = True
        else:
            if not self.last_step_had_tool_calls:
                self.consecutive_no_tool_calls += 1
            else:
                self.consecutive_no_tool_calls = 1
            self.last_step_had_tool_calls = False

        logger.debug(
            f"Tool call tracking: has_calls={has_tool_calls}, consecutive_no_calls={self.consecutive_no_tool_calls}"
        )

    def is_stuck_without_tools(self, max_consecutive_no_tools: int = 2) -> bool:
        """Check if agent is stuck (responding without tool calls repeatedly)."""
        return self.consecutive_no_tool_calls >= max_consecutive_no_tools

    def get_summary(self, limit: int = 12) -> str:
        """
        Get a compact summary of recent ReAct steps.

        Args:
            limit: Maximum number of steps to include

        Returns:
            Human-readable summary of steps
        """
        if not self.steps:
            return "No steps recorded."

        parts = []
        recent = self.steps[-limit:]
        start_idx = max(1, len(self.steps) - len(recent) + 1)

        for i, step in enumerate(recent, start=start_idx):
            if step.step_type == StepType.THOUGHT:
                snippet = step.content.strip().splitlines()[0][:120]
                parts.append(f"{i}. thought: {snippet}")
            elif step.step_type == StepType.ACTION:
                tool_name = step.tool_name or "tool"
                parts.append(f"{i}. action: {tool_name}")
            elif step.step_type == StepType.OBSERVATION:
                snippet = (step.content or "").strip().splitlines()[0][:120]
                parts.append(f"{i}. observation: {snippet}")
            elif step.step_type == StepType.ANSWER:
                snippet = step.content.strip().splitlines()[0][:120]
                parts.append(f"{i}. answer: {snippet}")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary representation."""
        return {
            "current_step": self.current_step,
            "steps": [step.to_dict() for step in self.steps],
            "tools_used": list(self.tools_used),
            "tool_stats": {
                name: {
                    "usage_count": stats.usage_count,
                    "last_used_step": stats.last_used_step,
                    "success_count": stats.success_count,
                    "error_count": stats.error_count,
                }
                for name, stats in self.tool_stats.items()
            },
            "search_attempts": self.search_attempts,
            "findings": self.findings,
            "finalize_requested": self.finalize_requested,
            "finalize_requested_at_step": self.finalize_requested_at_step,
            "should_stop": self.should_stop,
            "stop_reason": self.stop_reason,
            "consecutive_no_tool_calls": self.consecutive_no_tool_calls,
        }


class ReActStateMachine:
    """State machine for managing ReAct reasoning loop."""

    def __init__(self):
        """Initialize the state machine."""
        self.state = ReActState()

    def reset(self) -> None:
        """Reset the state machine to initial state."""
        self.state = ReActState()
        logger.debug("ReAct state machine reset")

    def get_state(self) -> ReActState:
        """Get the current state."""
        return self.state

    def should_continue(self, max_steps: int) -> bool:
        """Determine if the ReAct loop should continue."""
        if self.state.should_stop:
            return False

        if self.state.current_step >= max_steps:
            self.state.stop_with_reason(f"Maximum steps ({max_steps}) reached")
            return False

        return True

    def record_thought(self, content: str) -> None:
        """Record a thought step."""
        step = ReActStep(step_type=StepType.THOUGHT, content=content.strip())
        self.state.add_step(step)

    def record_action(self, tool_name: str, tool_input: Dict[str, Any]) -> None:
        """Record an action step."""
        step = ReActStep(
            step_type=StepType.ACTION,
            content=f"Used {tool_name}",
            tool_name=tool_name,
            tool_input=tool_input,
        )
        self.state.add_step(step)
        self.state.record_tool_usage(tool_name)

    def record_observation(self, content: str, tool_output: Any = None) -> None:
        """Record an observation step."""
        step = ReActStep(
            step_type=StepType.OBSERVATION, content=content, tool_output=tool_output
        )
        self.state.add_step(step)

    def record_answer(self, content: str) -> None:
        """Record a final answer step."""
        step = ReActStep(step_type=StepType.ANSWER, content=content.strip())
        self.state.add_step(step)
        self.state.stop_with_reason("Final answer provided")

    def get_context_prompt(self, available_tools: Set[str]) -> str:
        """Build context-aware prompt for next step."""
        tools_used = list(self.state.tools_used)
        search_attempts = self.state.search_attempts

        prompt = f"\n--- CONTEXT FROM PREVIOUS STEPS ---\n"
        prompt += f"You are now on step {self.state.current_step + 1}. "
        prompt += f"Previous tools used: {', '.join(tools_used)}\n"

        if search_attempts:
            prompt += "Previous search attempts:\n"
            for attempt in search_attempts[-3:]:  # Show last 3 attempts
                prompt += f"- {attempt}\n"

        # Progressive strategy suggestions based on step
        step = self.state.current_step
        if step == 1:
            prompt += "\n🎯 NEXT STRATEGY: The SQL analysis found no direct matches. "
            prompt += "Try ripgrep to search for window function patterns: 'SUM(', 'OVER (', 'LAG(' in .rb files."
        elif step == 2:
            prompt += "\n🎯 NEXT STRATEGY: Search in models/controllers for analytics methods. "
            prompt += "Use model_analyzer on Product model or controller_analyzer on reporting controllers."
        elif step == 3:
            prompt += "\n🎯 NEXT STRATEGY: Search for raw SQL execution. "
            prompt += "Use ripgrep to find 'connection.execute', 'find_by_sql', or ActiveRecord::Base patterns."
        elif step == 4:
            prompt += "\n🎯 NEXT STRATEGY: Look for custom SQL files or complex query builders. "
            prompt += "Try ast_grep for method definitions containing 'SELECT' or search for .sql files."

        return prompt
