"""
Test that the agent stops immediately when a tool returns an error.
"""
import pytest
from unittest.mock import Mock, MagicMock
from agent.react_rails_agent import ReactRailsAgent
from agent.config import AgentConfig


class TestToolErrorHandling:
    """Test error handling in the ReAct agent."""

    def test_tool_result_has_error_valid_json(self):
        """Test error detection in valid JSON results."""
        agent = ReactRailsAgent(config=AgentConfig.create_for_testing())

        # Valid error result
        result_with_error = '{"error": "Tool execution failed"}'
        assert agent._tool_result_has_error(result_with_error) is True

        # Valid non-error result
        result_without_error = '{"status": "success", "data": "result"}'
        assert agent._tool_result_has_error(result_without_error) is False

    def test_tool_result_has_error_invalid_json(self):
        """Test error detection with invalid JSON."""
        agent = ReactRailsAgent(config=AgentConfig.create_for_testing())

        # Invalid JSON
        invalid_json = "Not valid JSON"
        assert agent._tool_result_has_error(invalid_json) is False

        # Empty string
        assert agent._tool_result_has_error("") is False

    def test_extract_tool_error_valid(self):
        """Test error message extraction."""
        agent = ReactRailsAgent(config=AgentConfig.create_for_testing())

        # Valid error
        result = '{"error": "SQL analysis failed"}'
        error_msg = agent._extract_tool_error(result)
        assert error_msg == "SQL analysis failed"

        # Valid error with details
        result = '{"error": "AttributeError: missing attribute"}'
        error_msg = agent._extract_tool_error(result)
        assert "AttributeError" in error_msg

    def test_extract_tool_error_invalid(self):
        """Test error extraction with invalid input."""
        agent = ReactRailsAgent(config=AgentConfig.create_for_testing())

        # Invalid JSON
        error_msg = agent._extract_tool_error("Not JSON")
        assert error_msg == "Unknown error"

        # Valid JSON but no error key
        error_msg = agent._extract_tool_error('{"status": "ok"}')
        assert error_msg == "Unknown error"

    def test_agent_stops_on_tool_error(self):
        """Test that agent stops when a tool returns an error."""
        # Create mock session
        mock_session = Mock()
        mock_session.streaming_client = Mock()
        mock_session.provider = Mock()
        mock_session.max_tokens = 4096
        mock_session.provider_name = "bedrock"
        mock_session.usage_tracker = None

        # Create mock LLM response with tool error
        mock_result = Mock()
        mock_result.text = "I'll use the SQL search tool."
        mock_result.tokens = 100
        mock_result.cost = 0.0
        mock_result.error = None

        # Create mock tool call with error result
        mock_tool_call = Mock()
        mock_tool_call.name = "sql_rails_search"
        mock_tool_call.input = {"sql": "SELECT * FROM users"}
        mock_tool_call.id = "tool_123"
        mock_tool_call.result = '{"error": "QueryAnalysis object has no attribute has_offset"}'

        mock_result.tool_calls = [mock_tool_call]

        # Configure mock session to return our result
        mock_session.streaming_client.send_message.return_value = mock_result
        mock_session.provider.build_payload.return_value = {}
        mock_session.provider.map_events = lambda x: x

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(config=config, session=mock_session)

        # Process a message
        response = agent.process_message("Find the source of this SQL query")

        # Verify agent stopped with error
        assert agent.state_machine.state.should_stop is True
        assert "Tool execution failed" in agent.state_machine.state.stop_reason
        assert "has_offset" in agent.state_machine.state.stop_reason

    def test_agent_continues_on_success(self):
        """Test that agent continues when a tool returns success."""
        # Create mock session
        mock_session = Mock()
        mock_session.streaming_client = Mock()
        mock_session.provider = Mock()
        mock_session.max_tokens = 4096
        mock_session.provider_name = "bedrock"
        mock_session.usage_tracker = None

        # Create mock LLM response with successful tool result
        mock_result = Mock()
        mock_result.text = "Found the source code."
        mock_result.tokens = 100
        mock_result.cost = 0.0
        mock_result.error = None

        # Create mock tool call with success result
        mock_tool_call = Mock()
        mock_tool_call.name = "sql_rails_search"
        mock_tool_call.input = {"sql": "SELECT * FROM users"}
        mock_tool_call.id = "tool_123"
        mock_tool_call.result = '{"matches": [{"file": "app/models/user.rb", "line": 10}], "match_count": 1}'

        mock_result.tool_calls = [mock_tool_call]

        # Configure mock to return success then final response
        mock_session.streaming_client.send_message.side_effect = [
            mock_result,  # First call: tool execution
            Mock(text="Here is the source code location.", tool_calls=[], tokens=50, cost=0.0, error=None)  # Second call: final answer
        ]
        mock_session.provider.build_payload.return_value = {}
        mock_session.provider.map_events = lambda x: x

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(config=config, session=mock_session)

        # Process a message
        response = agent.process_message("Find the source of this SQL query")

        # Verify agent completed successfully (not stopped with error)
        if agent.state_machine.state.should_stop:
            # If stopped, it should be a normal completion, not an error
            assert "Tool execution failed" not in (agent.state_machine.state.stop_reason or "")
