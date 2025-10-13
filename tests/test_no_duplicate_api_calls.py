"""
Test that API errors do not trigger duplicate requests.

This test verifies that when an API call fails, the ReAct agent
stops immediately without making duplicate requests.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
from agent.react_rails_agent import ReactRailsAgent
from agent.config import AgentConfig
from llm.types import LLMResponse


class TestNoDuplicateAPICalls:
    """Test suite to verify no duplicate API calls on errors."""

    def test_api_error_stops_loop_without_retry(self):
        """Test that API errors stop the loop without making duplicate calls."""
        # Setup mock session
        mock_session = Mock()
        mock_session.provider = Mock()
        mock_session.provider.build_payload = Mock(return_value={})
        mock_session.streaming_client = Mock()
        mock_session.max_tokens = 4096
        mock_session.timeout = 30.0

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(session=mock_session, config=config)

        # Mock LLM client to return an error response
        error_response = LLMResponse(
            text="",
            tokens=0,
            cost=0.0,
            tool_calls=[],
            error="Network error: 400 Client Error: Bad Request"
        )

        # Track number of times call_llm is called
        call_count = 0
        original_call_llm = agent.llm_client.call_llm

        def mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return error_response

        agent.llm_client.call_llm = mock_call_llm

        # Execute query
        result = agent.process_message("test query")

        # Verify only ONE API call was made (no retry)
        assert call_count == 1, f"Expected 1 API call, but got {call_count}"

        # Verify the agent stopped and returned a response
        assert result is not None
        # When API errors occur early, the agent returns a message about no steps completed
        assert "no" in result.lower() or "completed" in result.lower()

    def test_exception_stops_loop_without_retry(self):
        """Test that exceptions stop the loop without making duplicate calls."""
        # Setup mock session
        mock_session = Mock()
        mock_session.provider = Mock()
        mock_session.provider.build_payload = Mock(return_value={})
        mock_session.streaming_client = Mock()
        mock_session.max_tokens = 4096
        mock_session.timeout = 30.0

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(session=mock_session, config=config)

        # Track number of times call_llm is called
        call_count = 0

        def mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # Raise an exception on first call
            raise RuntimeError("Simulated API failure")

        agent.llm_client.call_llm = mock_call_llm

        # Execute query
        result = agent.process_message("test query")

        # Verify only ONE API call was made (no retry after exception)
        assert call_count == 1, f"Expected 1 API call, but got {call_count}"

        # Verify the agent handled the error gracefully
        assert result is not None

    def test_successful_response_allows_multiple_steps(self):
        """Test that successful responses allow the loop to continue normally."""
        # Setup mock session
        mock_session = Mock()
        mock_session.provider = Mock()
        mock_session.provider.build_payload = Mock(return_value={})
        mock_session.streaming_client = Mock()
        mock_session.max_tokens = 4096
        mock_session.timeout = 30.0

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(session=mock_session, config=config)

        # Track API call count
        call_count = 0

        def mock_call_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            # Return successful response with final answer
            return LLMResponse(
                text="Final Answer: This is the response",
                tokens=100,
                cost=0.001,
                tool_calls=[],
                error=None
            )

        agent.llm_client.call_llm = mock_call_llm

        # Execute query
        result = agent.process_message("test query")

        # Should make at least one successful call
        assert call_count >= 1, f"Expected at least 1 API call, but got {call_count}"

        # Verify successful response
        assert result is not None
        assert "response" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
