"""
Tests for infinite loop prevention in ReAct agent.

These tests verify that the agent properly detects and handles:
1. Consecutive responses without tool calls (stuck agent)
2. Timeout after finalization request
3. Loop detection in tool usage
"""
import pytest
from agent.state_machine import ReActState, ReActStateMachine


class TestInfiniteLoopPrevention:
    """Test infinite loop detection and prevention."""

    def test_consecutive_no_tool_calls_detection(self):
        """Test detection of consecutive steps without tool calls."""
        state = ReActState()

        # First step with tool calls
        state.record_tool_call_status(has_tool_calls=True)
        assert state.consecutive_no_tool_calls == 0
        assert not state.is_stuck_without_tools()

        # Second step without tool calls
        state.record_tool_call_status(has_tool_calls=False)
        assert state.consecutive_no_tool_calls == 1
        assert not state.is_stuck_without_tools()

        # Third step without tool calls - should be stuck
        state.record_tool_call_status(has_tool_calls=False)
        assert state.consecutive_no_tool_calls == 2
        assert state.is_stuck_without_tools(max_consecutive_no_tools=2)

    def test_tool_calls_reset_consecutive_counter(self):
        """Test that making tool calls resets the consecutive counter."""
        state = ReActState()

        # Build up consecutive no-tool-calls
        state.record_tool_call_status(has_tool_calls=False)
        state.record_tool_call_status(has_tool_calls=False)
        assert state.consecutive_no_tool_calls == 2

        # Make tool call - should reset
        state.record_tool_call_status(has_tool_calls=True)
        assert state.consecutive_no_tool_calls == 0
        assert not state.is_stuck_without_tools()

    def test_finalization_timeout_detection(self):
        """Test detection of timeout after finalization request."""
        state = ReActState()
        state.current_step = 5

        # Not finalized yet
        assert not state.is_stuck_after_finalization()

        # Request finalization at step 5
        state.request_finalization()
        assert state.finalize_requested
        assert state.finalize_requested_at_step == 5

        # Step 6 - not stuck yet
        state.current_step = 6
        assert not state.is_stuck_after_finalization(max_steps_after_finalization=2)

        # Step 7 - still not stuck (exactly at threshold)
        state.current_step = 7
        assert state.is_stuck_after_finalization(max_steps_after_finalization=2)

    def test_finalization_timeout_with_custom_threshold(self):
        """Test finalization timeout with custom threshold."""
        state = ReActState()
        state.current_step = 10
        state.request_finalization()

        # Test with threshold of 3 steps
        state.current_step = 12
        assert not state.is_stuck_after_finalization(max_steps_after_finalization=3)

        state.current_step = 13
        assert state.is_stuck_after_finalization(max_steps_after_finalization=3)

    def test_stuck_detection_edge_cases(self):
        """Test edge cases in stuck detection."""
        state = ReActState()

        # Single no-tool-call should not trigger stuck
        state.record_tool_call_status(has_tool_calls=False)
        assert not state.is_stuck_without_tools(max_consecutive_no_tools=2)

        # Alternating tool calls and no-tool-calls should reset counter
        state.record_tool_call_status(has_tool_calls=False)
        state.record_tool_call_status(has_tool_calls=True)
        state.record_tool_call_status(has_tool_calls=False)
        assert state.consecutive_no_tool_calls == 1
        assert not state.is_stuck_without_tools(max_consecutive_no_tools=2)

    def test_state_machine_finalization_tracking(self):
        """Test that state machine properly tracks finalization."""
        sm = ReActStateMachine()

        # Initial state
        assert not sm.state.finalize_requested
        assert sm.state.finalize_requested_at_step is None

        # Record some steps
        sm.record_thought("Thinking...")
        sm.record_action("ripgrep", {"pattern": "test"})

        # Request finalization
        sm.state.request_finalization()
        assert sm.state.finalize_requested
        assert sm.state.finalize_requested_at_step == sm.state.current_step

    def test_to_dict_includes_new_fields(self):
        """Test that state serialization includes new tracking fields."""
        state = ReActState()
        state.current_step = 5
        state.request_finalization()
        state.record_tool_call_status(has_tool_calls=False)
        state.record_tool_call_status(has_tool_calls=False)

        state_dict = state.to_dict()

        assert "finalize_requested" in state_dict
        assert "finalize_requested_at_step" in state_dict
        assert "consecutive_no_tool_calls" in state_dict
        assert state_dict["finalize_requested"] is True
        assert state_dict["finalize_requested_at_step"] == 5
        assert state_dict["consecutive_no_tool_calls"] == 2

    def test_consecutive_tracking_with_immediate_tool_calls(self):
        """Test tracking when tool calls happen immediately."""
        state = ReActState()

        # Start with tool calls
        state.record_tool_call_status(has_tool_calls=True)
        state.record_tool_call_status(has_tool_calls=True)
        assert state.consecutive_no_tool_calls == 0

        # Then no tool calls
        state.record_tool_call_status(has_tool_calls=False)
        state.record_tool_call_status(has_tool_calls=False)
        assert state.consecutive_no_tool_calls == 2