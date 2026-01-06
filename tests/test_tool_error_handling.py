"""
Test tool error handling in the ReAct agent.

The agent classifies tool errors as:
- Critical: Agent stops immediately (e.g., "Project root not found", "Permission denied")
- Recoverable: Agent continues, LLM observes the error (e.g., "Path does not exist")
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

    def test_is_critical_tool_error_classification(self):
        """Test error classification as critical vs recoverable."""
        agent = ReactRailsAgent(config=AgentConfig.create_for_testing())

        # Critical errors - should return True (agent stops)
        critical_errors = [
            "Project root not found",
            "Path outside project root",
            "Permission denied: /etc/passwd",
            "Unknown tool: nonexistent_tool",
            "No project root configured",
        ]
        for error in critical_errors:
            assert agent._is_critical_tool_error(error) is True, f"Expected '{error}' to be critical"

        # Recoverable errors - should return False (agent continues)
        recoverable_errors = [
            "Path does not exist: app/jobs",
            "Not a directory: config/routes.rb",
            "No matches found",
            "Pattern is required",
            "Invalid input parameters",
            "Search timed out",
            "Starting line 100 exceeds file length (50 lines)",
            "QueryAnalysis object has no attribute has_offset",
            "File not found: missing.rb",
        ]
        for error in recoverable_errors:
            assert agent._is_critical_tool_error(error) is False, f"Expected '{error}' to be recoverable"

    def test_agent_stops_on_critical_tool_error(self):
        """Test that agent stops when a tool returns a critical error."""
        # Create mock session
        mock_session = Mock()
        mock_session.streaming_client = Mock()
        mock_session.provider = Mock()
        mock_session.max_tokens = 4096
        mock_session.provider_name = "bedrock"
        mock_session.usage_tracker = None

        # Create mock LLM response with critical tool error
        mock_result = Mock()
        mock_result.text = "I'll list the project directory."
        mock_result.tokens = 100
        mock_result.cost = 0.0
        mock_result.error = None

        # Create mock tool call with CRITICAL error result
        mock_tool_call = Mock()
        mock_tool_call.name = "list_directory"
        mock_tool_call.input = {"path": "../../../etc"}
        mock_tool_call.id = "tool_123"
        mock_tool_call.result = '{"error": "Path outside project root"}'

        mock_result.tool_calls = [mock_tool_call]

        # Configure mock session to return our result
        mock_session.streaming_client.send_message.return_value = mock_result
        mock_session.provider.build_payload.return_value = {}
        mock_session.provider.map_events = lambda x: x

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(config=config, session=mock_session)

        # Process a message
        response = agent.process_message("Show me the project structure")

        # Verify agent stopped with critical error
        assert agent.state_machine.state.should_stop is True
        assert "Tool execution failed" in agent.state_machine.state.stop_reason
        assert "Path outside project root" in agent.state_machine.state.stop_reason

    def test_agent_continues_on_recoverable_tool_error(self):
        """Test that agent continues when a tool returns a recoverable error."""
        # Create mock session
        mock_session = Mock()
        mock_session.streaming_client = Mock()
        mock_session.provider = Mock()
        mock_session.max_tokens = 4096
        mock_session.provider_name = "bedrock"
        mock_session.usage_tracker = None

        # Create mock LLM response with recoverable tool error
        mock_result = Mock()
        mock_result.text = "I'll check the app/jobs directory."
        mock_result.tokens = 100
        mock_result.cost = 0.0
        mock_result.error = None

        # Create mock tool call with RECOVERABLE error result
        mock_tool_call = Mock()
        mock_tool_call.name = "list_directory"
        mock_tool_call.input = {"path": "app/jobs"}
        mock_tool_call.id = "tool_123"
        mock_tool_call.result = '{"error": "Path does not exist: app/jobs"}'

        mock_result.tool_calls = [mock_tool_call]

        # Configure mock - first returns error, then LLM provides answer
        final_result = Mock()
        final_result.text = "The app/jobs directory doesn't exist. Let me check elsewhere."
        final_result.tokens = 50
        final_result.cost = 0.0
        final_result.error = None
        final_result.tool_calls = []

        mock_session.streaming_client.send_message.side_effect = [mock_result, final_result]
        mock_session.provider.build_payload.return_value = {}
        mock_session.provider.map_events = lambda x: x

        # Create agent
        config = AgentConfig.create_for_testing()
        agent = ReactRailsAgent(config=config, session=mock_session)

        # Process a message
        response = agent.process_message("Find background job implementations")

        # Verify agent did NOT stop with error (it should continue and eventually finish normally)
        if agent.state_machine.state.stop_reason:
            assert "Tool execution failed" not in agent.state_machine.state.stop_reason
            assert "Path does not exist" not in agent.state_machine.state.stop_reason

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
