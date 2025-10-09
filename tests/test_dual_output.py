"""
Test dual-layer output architecture for UI vs LLM context.

Verifies that tool execution returns both full results (for LLM conversation)
and compact results (for UI display).
"""
import pytest
from agent_tool_executor import AgentToolExecutor
from llm.tool_execution import ToolExecutionService
from llm.types import ToolCall
from tools.base_tool import BaseTool
from tools.executor import ToolExecutor


class MockTool(BaseTool):
    """Mock tool that returns different full and compact outputs."""

    def __init__(self, tool_name="mock_tool", debug=False):
        super().__init__(debug=debug)
        self._name = tool_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Mock tool for testing dual output"

    def execute(self, params):
        """Return full output with lots of details."""
        return {
            "summary": "Mock result",
            "details": "This is a very long detailed output that contains lots of information...",
            "data": list(range(100)),  # Lots of data
            "metadata": {"foo": "bar", "baz": "qux"}
        }

    def create_compact_output(self, full_result):
        """Return compact version for UI."""
        return {
            "summary": full_result["summary"],
            "hint": "Use --verbose to see full details"
        }


def test_agent_tool_executor_returns_both_versions():
    """Test that AgentToolExecutor returns both full and compact results."""
    # Setup
    tool = MockTool()
    executor = AgentToolExecutor({"mock_tool": tool})

    # Execute (non-verbose mode)
    result = executor.execute_tool("mock_tool", {})

    # Verify both versions exist
    assert "content" in result, "Should have full content for LLM"
    assert "display" in result, "Should have display content for UI"

    # Verify they are different
    assert result["content"] != result["display"], "Full and compact should differ"

    # Verify full version has all data
    full_content = result["content"]
    assert "data" in full_content or "[100" in full_content, "Full should have data list"

    # Verify compact version is shorter
    display_content = result["display"]
    assert "hint" in display_content or "verbose" in display_content, "Compact should have hint"


def test_agent_tool_executor_verbose_mode():
    """Test that verbose mode uses full output for both."""
    # Setup with debug enabled
    tool = MockTool(debug=True)
    executor = AgentToolExecutor({"mock_tool": tool})

    # Execute (verbose mode)
    result = executor.execute_tool("mock_tool", {})

    # In verbose mode, both should be the same (full)
    assert result["content"] == result["display"], "Verbose mode should use full for both"


def test_tool_execution_service_populates_both_fields():
    """Test that ToolExecutionService populates both result and display_result."""
    # Setup
    tool = MockTool()
    # Use AgentToolExecutor which holds our agent tools
    tool_executor = AgentToolExecutor({"mock_tool": tool})

    service = ToolExecutionService(tool_executor)

    # Mock response data with tool call
    response_data = {
        "content": [
            {
                "type": "tool_use",
                "toolUse": [
                    {
                        "id": "test-123",
                        "name": "mock_tool",
                        "input": {}
                    }
                ]
            }
        ]
    }

    # Mock parser
    class MockParser:
        def extract_tool_calls(self, data):
            tool_uses = []
            for block in data.get("content", []):
                if block.get("type") == "tool_use":
                    for tc in block.get("toolUse", []):
                        tool_uses.append({
                            "id": tc["id"],
                            "name": tc["name"],
                            "input": tc.get("input", {})
                        })
            return tool_uses

    parser = MockParser()

    # Execute
    tool_calls = service.extract_and_execute(response_data, parser)

    # Verify
    assert len(tool_calls) == 1, "Should have one tool call"

    tool_call = tool_calls[0]
    assert isinstance(tool_call, ToolCall), "Should be ToolCall object"
    assert tool_call.result, "Should have result field (full)"
    assert tool_call.display_result, "Should have display_result field (compact)"

    # Verify they are different
    assert tool_call.result != tool_call.display_result, "Result and display should differ"

    # Verify full result has more data
    assert "data" in tool_call.result or "[100" in tool_call.result, "Full should have data"
    assert "hint" in tool_call.display_result or "verbose" in tool_call.display_result, "Compact should have hint"


def test_tool_call_fallback_when_display_empty():
    """Test that UI falls back to result when display_result is empty."""
    tool_call = ToolCall(
        id="test-123",
        name="test",
        input={},
        result="Full result text",
        display_result=""  # Empty
    )

    # Simulate UI logic from llm_client.py:174
    display_text = tool_call.display_result if tool_call.display_result else tool_call.result

    assert display_text == "Full result text", "Should fall back to result when display is empty"


def test_error_handling_sets_both_fields():
    """Test that errors set both result and display_result."""
    # Setup with a tool that will fail
    class FailingTool(BaseTool):
        @property
        def name(self) -> str:
            return "failing_tool"

        @property
        def description(self) -> str:
            return "Tool that fails for testing"

        def execute(self, params):
            raise ValueError("Simulated error")

    tool = FailingTool()
    executor = AgentToolExecutor({"failing_tool": tool})

    # Execute
    result = executor.execute_tool("failing_tool", {})

    # Both should contain the error
    assert "Error executing" in result["content"], "Full should have error"
    assert "Error executing" in result["display"], "Display should have error"
    assert result["content"] == result["display"], "Error messages should be identical"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
