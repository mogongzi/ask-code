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

    # API turn tracking (counts LLM API calls, not ReAct steps)
    api_turns: int = 0

    # Tool usage tracking
    tools_used: Set[str] = field(default_factory=set)
    tool_stats: Dict[str, ToolUsageStats] = field(default_factory=dict)
    search_attempts: List[str] = field(default_factory=list)

    # Results tracking
    findings: List[str] = field(default_factory=list)

    # Control flags
    finalize_requested: bool = False
    finalize_requested_at_step: Optional[int] = None
    should_stop: bool = False
    stop_reason: Optional[str] = None

    # Stuck detection
    consecutive_no_tool_calls: int = 0
    last_step_had_tool_calls: bool = False

    def increment_api_turn(self) -> int:
        """Increment and return the API turn count."""
        self.api_turns += 1
        return self.api_turns

    def add_step(self, step: ReActStep) -> None:
        """
        Add a new step to the state with transition validation.

        Valid transitions:
        - THOUGHT can follow any step (new reasoning)
        - ACTION must follow THOUGHT (act based on reasoning)
        - OBSERVATION must follow ACTION (observe result of action)
        - ANSWER can follow any step (final answer)
        """
        # Validate state transition
        if self.steps:
            last_step = self.steps[-1]
            self._validate_transition(last_step.step_type, step.step_type)

        step.step_number = len(self.steps) + 1
        self.steps.append(step)
        self.current_step = step.step_number
        logger.debug(f"Added step {step.step_number}: {step.step_type.value}")

    def _validate_transition(self, from_type: StepType, to_type: StepType) -> None:
        """
        Validate that a step transition is valid in the ReAct pattern.

        Args:
            from_type: Previous step type
            to_type: New step type

        Raises:
            ValueError: If transition is invalid (in debug mode only warns)
        """
        # ANSWER can always be added (final step)
        if to_type == StepType.ANSWER:
            return

        # THOUGHT can always be added (new reasoning cycle)
        if to_type == StepType.THOUGHT:
            return

        # ACTION should follow THOUGHT (but we're lenient for now)
        if to_type == StepType.ACTION:
            if from_type not in [StepType.THOUGHT, StepType.OBSERVATION]:
                logger.warning(
                    f"Unusual transition: {from_type.value} → {to_type.value}. "
                    f"Expected THOUGHT before ACTION."
                )
            return

        # OBSERVATION must follow ACTION
        if to_type == StepType.OBSERVATION:
            if from_type != StepType.ACTION:
                logger.warning(
                    f"Invalid transition: {from_type.value} → {to_type.value}. "
                    f"OBSERVATION must follow ACTION."
                )
            return

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
        """
        Detect exact infinite loops only.

        Only returns True if the EXACT same action has been repeated
        multiple times in a row. We trust the LLM to naturally vary
        its approach - only intervene for true infinite loops.
        """
        # Only force if we're stuck in an EXACT loop (same action 3+ times)
        if len(self.search_attempts) >= 3:
            recent = self.search_attempts[-3:]
            if len(set(recent)) == 1:  # All 3 are identical
                logger.info(f"Exact infinite loop detected: {recent[0]} repeated 3x")
                return True

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

    def get_reasoning_trail(self) -> List[str]:
        """
        Extract all THOUGHT step content as reasoning texts.

        Returns:
            List of reasoning text strings in chronological order
        """
        return [
            step.content
            for step in self.steps
            if step.step_type == StepType.THOUGHT and step.content.strip()
        ]

    def get_complete_reasoning_trail(self) -> List[Dict[str, Any]]:
        """
        Get complete ReAct cycles with thought, action(s), and observation(s).

        Groups steps into cycles, handling:
        - THOUGHT → ACTION(s) → OBSERVATION(s): standard ReAct cycle
        - ACTION(s) → OBSERVATION(s) without THOUGHT: tool calls without reasoning text
        - Parallel tool calls: multiple ACTIONs collected into single cycle

        Returns:
            List of cycle dictionaries with keys:
            - thought: reasoning content (empty string if no THOUGHT)
            - tools: list of {tool_name, tool_input, tool_output} dicts
            - tool_name, tool_input, tool_output: first tool (backward compatibility)
        """
        cycles = []
        i = 0
        while i < len(self.steps):
            step = self.steps[i]

            # Start a new cycle from THOUGHT or ACTION
            if step.step_type == StepType.THOUGHT:
                # Standard cycle: THOUGHT → ACTION(s) → OBSERVATION(s)
                cycle = {
                    "thought": step.content,
                    "tools": []
                }
                next_idx = i + 1
            elif step.step_type == StepType.ACTION:
                # Orphaned action: ACTION(s) → OBSERVATION(s) without THOUGHT
                # This happens when LLM makes tool calls without reasoning text
                cycle = {
                    "thought": "",  # No reasoning text for this cycle
                    "tools": []
                }
                next_idx = i  # Start collecting from current ACTION
            else:
                # Skip orphaned OBSERVATIONs (shouldn't happen in normal flow)
                i += 1
                continue

            # Collect ALL consecutive ACTIONs (handles parallel tool calls)
            actions = []
            while next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.ACTION:
                actions.append(self.steps[next_idx])
                next_idx += 1

            # Collect ALL consecutive OBSERVATIONs
            observations = []
            while next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.OBSERVATION:
                observations.append(self.steps[next_idx])
                next_idx += 1

            # Pair actions with observations (by order)
            for j, action in enumerate(actions):
                tool_info = {
                    "tool_name": action.tool_name,
                    "tool_input": action.tool_input,
                    "tool_output": observations[j].content if j < len(observations) else None
                }
                cycle["tools"].append(tool_info)

            # Backward compatibility: set first tool as top-level fields
            if cycle["tools"]:
                first_tool = cycle["tools"][0]
                cycle["tool_name"] = first_tool["tool_name"]
                cycle["tool_input"] = first_tool["tool_input"]
                cycle["tool_output"] = first_tool["tool_output"]

            cycles.append(cycle)
            i = next_idx  # Move past the processed steps
        return cycles

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary representation."""
        return {
            "current_step": self.current_step,
            "api_turns": self.api_turns,
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

    def get_context_prompt(self) -> str:
        """
        Build minimal context prompt for next step.

        Only provides step number and recent activity summary.
        The LLM reasons freely based on the system prompt.
        """
        lines = [
            f"\nStep {self.state.current_step + 1}: continue from prior reasoning."
        ]

        if self.state.tools_used:
            lines.append(f"Tools used so far: {', '.join(self.state.tools_used)}.")

        if self.state.search_attempts:
            recent_attempts = "; ".join(self.state.search_attempts[-2:])
            lines.append(f"Recent searches: {recent_attempts}.")

        return " ".join(lines)
