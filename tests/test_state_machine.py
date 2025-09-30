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
        assert state.step_results == {}
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