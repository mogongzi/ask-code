"""
Tests for agent.state_machine.ReActStateMachine
"""
import pytest
from unittest.mock import Mock
from datetime import datetime

from agent.state_machine import ReActStateMachine, ToolUsageStats, ReActState, ReActStep, StepType


class TestToolUsageStats:
    """Test suite for ToolUsageStats."""

    def test_initialization(self):
        """Test ToolUsageStats initialization."""
        stats = ToolUsageStats(name="test_tool")

        assert stats.name == "test_tool"
        assert stats.usage_count == 0
        assert stats.last_used_step == 0
        assert stats.success_count == 0
        assert stats.error_count == 0

    def test_initialization_with_values(self):
        """Test ToolUsageStats initialization with custom values."""
        stats = ToolUsageStats(
            name="ripgrep",
            usage_count=5,
            last_used_step=10,
            success_count=4,
            error_count=1
        )

        assert stats.name == "ripgrep"
        assert stats.usage_count == 5
        assert stats.last_used_step == 10
        assert stats.success_count == 4
        assert stats.error_count == 1

    def test_dataclass_behavior(self):
        """Test that ToolUsageStats behaves as a dataclass."""
        stats1 = ToolUsageStats(name="tool1", usage_count=3)
        stats2 = ToolUsageStats(name="tool1", usage_count=3)
        stats3 = ToolUsageStats(name="tool2", usage_count=3)

        assert stats1 == stats2  # Same values should be equal
        assert stats1 != stats3  # Different names should not be equal


class TestReActState:
    """Test suite for ReActState."""

    def test_initialization(self):
        """Test ReActState initialization."""
        state = ReActState()

        assert state.current_step == 0
        assert state.steps == []
        assert state.tools_used == set()
        assert state.tool_stats == {}
        assert state.search_attempts == []
        assert state.findings == []
        assert state.finalize_requested is False
        assert state.should_stop is False
        assert state.stop_reason is None

    def test_add_step(self):
        """Test adding steps to state."""
        state = ReActState()
        step = ReActStep(step_type=StepType.THOUGHT, content="Test thought")

        state.add_step(step)

        assert len(state.steps) == 1
        assert state.steps[0] == step

    def test_add_multiple_steps(self):
        """Test adding multiple steps."""
        state = ReActState()
        step1 = ReActStep(step_type=StepType.THOUGHT, content="Thought 1")
        step2 = ReActStep(step_type=StepType.ACTION, content="Action 1")

        state.add_step(step1)
        state.add_step(step2)

        assert len(state.steps) == 2
        assert state.steps[0] == step1
        assert state.steps[1] == step2

    def test_tools_used_tracking(self):
        """Test tool usage tracking."""
        state = ReActState()

        # Initially no tools used
        assert len(state.tools_used) == 0

        # Add some tools
        state.tools_used.add("ripgrep")
        state.tools_used.add("ast_grep")

        assert len(state.tools_used) == 2
        assert "ripgrep" in state.tools_used
        assert "ast_grep" in state.tools_used

    def test_tool_stats_tracking(self):
        """Test tool statistics tracking."""
        state = ReActState()

        # Add tool stats
        state.tool_stats["ripgrep"] = ToolUsageStats(
            name="ripgrep",
            usage_count=3,
            success_count=2,
            error_count=1
        )

        assert len(state.tool_stats) == 1
        assert "ripgrep" in state.tool_stats
        assert state.tool_stats["ripgrep"].usage_count == 3


class TestReActStateMachine:
    """Test suite for ReActStateMachine."""

    def test_initialization(self):
        """Test state machine initialization."""
        state_machine = ReActStateMachine()

        assert state_machine.state is not None
        assert isinstance(state_machine.state, ReActState)
        assert state_machine.state.current_step == 0

    def test_reset(self):
        """Test resetting state machine."""
        state_machine = ReActStateMachine()

        # Modify the state
        state_machine.state.current_step = 5
        state_machine.state.tools_used.add("ripgrep")

        # Reset
        state_machine.reset()

        # Should be back to initial state
        assert state_machine.state.current_step == 0
        assert len(state_machine.state.tools_used) == 0

    def test_get_state(self):
        """Test getting current state."""
        state_machine = ReActStateMachine()

        state = state_machine.get_state()

        assert isinstance(state, ReActState)
        assert state is state_machine.state

    def test_should_continue_with_no_stop_flag(self):
        """Test continuation when should_stop is False."""
        state_machine = ReActStateMachine()

        # Should continue when not stopped and under max steps
        should_continue = state_machine.should_continue(max_steps=10)
        assert should_continue is True

    def test_should_continue_with_stop_flag(self):
        """Test continuation when should_stop is True."""
        state_machine = ReActStateMachine()
        state_machine.state.should_stop = True

        # Should not continue when stopped
        should_continue = state_machine.should_continue(max_steps=10)
        assert should_continue is False

    def test_should_continue_at_max_steps(self):
        """Test continuation at max steps."""
        state_machine = ReActStateMachine()
        state_machine.state.current_step = 10

        # Should not continue when at max steps
        should_continue = state_machine.should_continue(max_steps=10)
        assert should_continue is False

    def test_step_progression(self):
        """Test step progression tracking."""
        state_machine = ReActStateMachine()

        # Add some steps
        step1 = ReActStep(step_type=StepType.THOUGHT, content="Think")
        step2 = ReActStep(step_type=StepType.ACTION, content="Act")

        state_machine.state.add_step(step1)
        state_machine.state.current_step = 1

        state_machine.state.add_step(step2)
        state_machine.state.current_step = 2

        assert len(state_machine.state.steps) == 2
        assert state_machine.state.current_step == 2

    def test_tool_tracking_workflow(self):
        """Test complete tool tracking workflow."""
        state_machine = ReActStateMachine()

        # Track tool usage
        state_machine.state.tools_used.add("ripgrep")
        state_machine.state.tool_stats["ripgrep"] = ToolUsageStats(
            name="ripgrep",
            usage_count=1,
            last_used_step=1,
            success_count=1,
            error_count=0
        )

        assert "ripgrep" in state_machine.state.tools_used
        assert state_machine.state.tool_stats["ripgrep"].usage_count == 1

    def test_state_persistence_through_operations(self):
        """Test that state persists through various operations."""
        state_machine = ReActStateMachine()

        # Perform various operations
        state_machine.state.current_step = 3
        state_machine.state.tools_used.add("ripgrep")
        state_machine.state.findings.append("Found authentication code")

        # Get state and verify persistence
        state = state_machine.get_state()
        assert state.current_step == 3
        assert "ripgrep" in state.tools_used
        assert "Found authentication code" in state.findings

    def test_finalize_flag_handling(self):
        """Test finalize request flag handling."""
        state_machine = ReActStateMachine()

        # Initially not finalized
        assert state_machine.state.finalize_requested is False

        # Set finalize flag
        state_machine.state.finalize_requested = True
        assert state_machine.state.finalize_requested is True

    def test_stop_reason_tracking(self):
        """Test stop reason tracking."""
        state_machine = ReActStateMachine()

        # Initially no stop reason
        assert state_machine.state.stop_reason is None

        # Set stop reason
        state_machine.state.should_stop = True
        state_machine.state.stop_reason = "Max steps reached"

        assert state_machine.state.should_stop is True
        assert state_machine.state.stop_reason == "Max steps reached"


class TestGetReasoningTrail:
    """Test suite for get_reasoning_trail() method."""

    def test_get_reasoning_trail_with_thought_steps(self):
        """Test extracting reasoning from THOUGHT steps."""
        state = ReActState()

        # Add various steps
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="First thought"))
        state.add_step(ReActStep(step_type=StepType.ACTION, content="Action", tool_name="ripgrep"))
        state.add_step(ReActStep(step_type=StepType.OBSERVATION, content="Result"))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Second thought"))
        state.add_step(ReActStep(step_type=StepType.ANSWER, content="Final answer"))

        reasoning = state.get_reasoning_trail()

        assert len(reasoning) == 2
        assert reasoning[0] == "First thought"
        assert reasoning[1] == "Second thought"

    def test_get_reasoning_trail_empty(self):
        """Test reasoning trail with no THOUGHT steps."""
        state = ReActState()
        state.add_step(ReActStep(step_type=StepType.ACTION, content="Action", tool_name="ripgrep"))

        reasoning = state.get_reasoning_trail()
        assert reasoning == []

    def test_get_reasoning_trail_no_steps(self):
        """Test reasoning trail with no steps at all."""
        state = ReActState()

        reasoning = state.get_reasoning_trail()
        assert reasoning == []

    def test_get_reasoning_trail_filters_empty_content(self):
        """Test that empty thought content is filtered out."""
        state = ReActState()

        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Valid thought"))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content=""))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="   "))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Another valid thought"))

        reasoning = state.get_reasoning_trail()

        assert len(reasoning) == 2
        assert reasoning[0] == "Valid thought"
        assert reasoning[1] == "Another valid thought"

    def test_get_reasoning_trail_preserves_order(self):
        """Test that reasoning steps are in chronological order."""
        state = ReActState()

        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="First"))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Second"))
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Third"))

        reasoning = state.get_reasoning_trail()

        assert reasoning == ["First", "Second", "Third"]


class TestGetCompleteReasoningTrail:
    """Test suite for get_complete_reasoning_trail() method."""

    def test_complete_cycle(self):
        """Test extracting complete THOUGHT → ACTION → OBSERVATION cycles."""
        state = ReActState()

        # Add a complete cycle
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Let me search"))
        state.add_step(ReActStep(
            step_type=StepType.ACTION,
            content="Used ripgrep",
            tool_name="ripgrep",
            tool_input={"pattern": "test"}
        ))
        state.add_step(ReActStep(
            step_type=StepType.OBSERVATION,
            content="Found 5 matches"
        ))

        cycles = state.get_complete_reasoning_trail()

        assert len(cycles) == 1
        assert cycles[0]["thought"] == "Let me search"
        assert cycles[0]["tool_name"] == "ripgrep"
        assert cycles[0]["tool_input"] == {"pattern": "test"}
        assert cycles[0]["tool_output"] == "Found 5 matches"

    def test_multiple_cycles(self):
        """Test extracting multiple complete cycles."""
        state = ReActState()

        # First cycle
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="First thought"))
        state.add_step(ReActStep(
            step_type=StepType.ACTION,
            content="Used tool1",
            tool_name="tool1",
            tool_input={"arg": "value1"}
        ))
        state.add_step(ReActStep(step_type=StepType.OBSERVATION, content="Result 1"))

        # Second cycle
        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Second thought"))
        state.add_step(ReActStep(
            step_type=StepType.ACTION,
            content="Used tool2",
            tool_name="tool2",
            tool_input={"arg": "value2"}
        ))
        state.add_step(ReActStep(step_type=StepType.OBSERVATION, content="Result 2"))

        cycles = state.get_complete_reasoning_trail()

        assert len(cycles) == 2
        assert cycles[0]["thought"] == "First thought"
        assert cycles[0]["tool_name"] == "tool1"
        assert cycles[1]["thought"] == "Second thought"
        assert cycles[1]["tool_name"] == "tool2"

    def test_thought_only_cycle(self):
        """Test that thoughts without actions are included."""
        state = ReActState()

        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="Just a thought"))

        cycles = state.get_complete_reasoning_trail()

        assert len(cycles) == 1
        assert cycles[0]["thought"] == "Just a thought"
        assert "tool_name" not in cycles[0]

    def test_empty_state(self):
        """Test empty state returns empty list."""
        state = ReActState()

        cycles = state.get_complete_reasoning_trail()

        assert cycles == []

    def test_thought_with_action_no_observation(self):
        """Test thought with action but no observation."""
        state = ReActState()

        state.add_step(ReActStep(step_type=StepType.THOUGHT, content="My thought"))
        state.add_step(ReActStep(
            step_type=StepType.ACTION,
            content="Used tool",
            tool_name="ripgrep",
            tool_input={"pattern": "foo"}
        ))

        cycles = state.get_complete_reasoning_trail()

        assert len(cycles) == 1
        assert cycles[0]["thought"] == "My thought"
        assert cycles[0]["tool_name"] == "ripgrep"
        assert "tool_output" not in cycles[0]