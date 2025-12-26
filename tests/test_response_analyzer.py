"""
Tests for the simplified ResponseAnalyzer.

The analyzer now trusts LLM judgment: if LLM stops calling tools
and provides substantive text, it's done.
"""

import pytest
from unittest.mock import Mock, MagicMock
from agent.response_analyzer import ResponseAnalyzer, AnalysisResult
from agent.state_machine import ReActState


class TestAnalysisResult:
    """Tests for the AnalysisResult dataclass."""

    def test_analysis_result_creation(self):
        """Test that AnalysisResult can be created with required fields."""
        result = AnalysisResult(
            is_final=True,
            confidence="high",
            reason="Test reason",
            suggestions=["suggestion1"],
            has_concrete_results=True
        )

        assert result.is_final is True
        assert result.confidence == "high"
        assert result.reason == "Test reason"
        assert result.suggestions == ["suggestion1"]
        assert result.has_concrete_results is True


class TestResponseAnalyzer:
    """Tests for the simplified ResponseAnalyzer class."""

    def test_initialization(self):
        """Test that ResponseAnalyzer initializes correctly."""
        analyzer = ResponseAnalyzer()
        assert analyzer is not None
        assert analyzer.MIN_SUBSTANTIVE_LENGTH == 200

    def test_analyze_response_final_when_no_tools_and_substantive(self):
        """Test that response is final when LLM stops calling tools and provides substantive text."""
        analyzer = ResponseAnalyzer()

        # Create a state where LLM has stopped calling tools
        state = ReActState()
        state.consecutive_no_tool_calls = 1

        # Long response (> 200 chars)
        response = "I found the source code. " * 20  # ~500 chars

        result = analyzer.analyze_response(response, state, step=5)

        assert result.is_final is True
        assert result.confidence == "high"
        assert "substantive answer" in result.reason.lower()

    def test_analyze_response_not_final_when_tool_calls_active(self):
        """Test that response is not final when LLM is still calling tools."""
        analyzer = ResponseAnalyzer()

        # Create a state where LLM is still using tools
        state = ReActState()
        state.consecutive_no_tool_calls = 0

        response = "Let me search for more information about this query."

        result = analyzer.analyze_response(response, state, step=3)

        assert result.is_final is False

    def test_analyze_response_not_final_when_response_too_short(self):
        """Test that short responses are not considered final."""
        analyzer = ResponseAnalyzer()

        state = ReActState()
        state.consecutive_no_tool_calls = 1

        # Short response (< 200 chars)
        response = "Found it in app/models/user.rb"  # ~30 chars

        result = analyzer.analyze_response(response, state, step=5)

        assert result.is_final is False

    def test_has_high_quality_tool_results_delegates_to_state(self):
        """Test that has_high_quality_tool_results delegates to ReActState."""
        analyzer = ResponseAnalyzer()

        mock_state = Mock(spec=ReActState)
        mock_state.has_high_quality_results.return_value = True

        result = analyzer.has_high_quality_tool_results(mock_state)

        assert result is True
        mock_state.has_high_quality_results.assert_called_once()

    def test_should_force_different_tool_exact_loop(self):
        """Test that should_force_different_tool detects exact infinite loops."""
        analyzer = ResponseAnalyzer()

        state = ReActState()
        # Same action repeated 3 times
        state.search_attempts = [
            "Step 1: Used ripgrep",
            "Step 1: Used ripgrep",
            "Step 1: Used ripgrep",
        ]

        result = analyzer.should_force_different_tool(state, step=5, repetition_limit=3)

        assert result is True

    def test_should_force_different_tool_no_loop(self):
        """Test that varied actions don't trigger force."""
        analyzer = ResponseAnalyzer()

        state = ReActState()
        state.search_attempts = [
            "Step 1: Used ripgrep",
            "Step 2: Used model_analyzer",
            "Step 3: Used ripgrep",
        ]

        result = analyzer.should_force_different_tool(state, step=5, repetition_limit=3)

        assert result is False

    def test_generate_finalization_prompt(self):
        """Test that finalization prompt is generated."""
        analyzer = ResponseAnalyzer()

        prompt = analyzer.generate_finalization_prompt()

        assert "final answer" in prompt.lower()
        assert len(prompt) > 20

    def test_generate_tool_constraint_prompt(self):
        """Test that constraint prompt is generated for stuck loops."""
        analyzer = ResponseAnalyzer()

        state = ReActState()
        state.tools_used = {"ripgrep"}

        available_tools = {"ripgrep", "model_analyzer", "file_reader"}

        prompt = analyzer.generate_tool_constraint_prompt(state, available_tools)

        assert "repeating" in prompt.lower() or "different" in prompt.lower()
        assert "model_analyzer" in prompt or "file_reader" in prompt

    def test_analyze_response_with_planning_tool_param_ignored(self):
        """Test that planning_tool parameter is accepted but ignored."""
        analyzer = ResponseAnalyzer()

        state = ReActState()
        state.consecutive_no_tool_calls = 1

        response = "Found the code! " * 20

        # Should not raise even with planning_tool param
        result = analyzer.analyze_response(
            response, state, step=5, planning_tool=Mock()
        )

        assert result is not None
