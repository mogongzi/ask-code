"""
Test that tool execution works correctly without console UI output.

The old "⚙ Using tool..." messages have been replaced with the live Explored display.
These tests verify that tool execution still works and doesn't produce legacy UI output.
"""
import pytest
import time
from io import StringIO
from llm.tool_execution import ToolExecutionService
from agent_tool_executor import AgentToolExecutor
from tools.base_tool import BaseTool
from rich.console import Console


class SlowTool(BaseTool):
    """Mock tool that takes time to execute."""

    @property
    def name(self) -> str:
        return "slow_tool"

    @property
    def description(self) -> str:
        return "Tool that takes time to execute"

    def execute(self, params):
        """Sleep for a bit to simulate slow execution."""
        time.sleep(0.5)  # 500ms delay
        return {"result": "Done after delay"}

    def create_compact_output(self, full_result):
        return {"result": "Done"}


def test_tool_executes_without_console_output():
    """Verify that tool execution doesn't produce legacy UI output."""
    # Setup
    tool = SlowTool()
    executor = AgentToolExecutor({"slow_tool": tool})

    # Capture console output
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)

    service = ToolExecutionService(executor, console=console)

    # Mock response data
    response_data = {
        "content": [
            {
                "type": "tool_use",
                "toolUse": [
                    {
                        "id": "test-123",
                        "name": "slow_tool",
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

    # Record start time
    start = time.time()

    # Execute (this will take 500ms)
    tool_calls = service.extract_and_execute(response_data, parser)

    # Record end time
    elapsed = time.time() - start

    # Get captured output
    console_output = output.getvalue()

    # Verify execution took at least 500ms (confirming the sleep happened)
    assert elapsed >= 0.5, f"Tool should have taken at least 500ms, took {elapsed*1000:.0f}ms"

    # Verify NO legacy "Using tool..." message (removed in favor of Explored display)
    assert "Using slow_tool tool" not in console_output, \
        "Should NOT show legacy 'Using tool...' message (replaced by Explored display)"

    # Verify we got a ToolCall result
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "slow_tool"


def test_multiple_tools_execute_without_console_output():
    """Verify that multiple tools execute without legacy UI output."""

    class QuickTool(BaseTool):
        def __init__(self, tool_name):
            super().__init__()
            self._name = tool_name

        @property
        def name(self) -> str:
            return self._name

        @property
        def description(self) -> str:
            return f"Quick tool {self._name}"

        def execute(self, params):
            time.sleep(0.1)  # Small delay
            return {"result": f"Result from {self._name}"}

        def create_compact_output(self, full_result):
            return {"summary": full_result["result"]}

    # Setup
    tool1 = QuickTool("tool_1")
    tool2 = QuickTool("tool_2")
    executor = AgentToolExecutor({"tool_1": tool1, "tool_2": tool2})

    # Capture output
    output = StringIO()
    console = Console(file=output, force_terminal=True, width=120)

    service = ToolExecutionService(executor, console=console)

    # Mock response with 2 tools
    response_data = {
        "content": [
            {
                "type": "tool_use",
                "toolUse": [
                    {"id": "test-1", "name": "tool_1", "input": {}},
                    {"id": "test-2", "name": "tool_2", "input": {}}
                ]
            }
        ]
    }

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
    tool_calls = service.extract_and_execute(response_data, parser)

    # Get output
    console_output = output.getvalue()

    # Verify NO legacy "Using tool..." messages (replaced by Explored display)
    assert "Using tool_1 tool" not in console_output, \
        "Should NOT show legacy 'Using tool...' message for tool_1"
    assert "Using tool_2 tool" not in console_output, \
        "Should NOT show legacy 'Using tool...' message for tool_2"

    # Verify both tools executed
    assert len(tool_calls) == 2
    assert tool_calls[0].name == "tool_1"
    assert tool_calls[1].name == "tool_2"


def test_on_tool_start_callback_is_invoked():
    """Verify that on_tool_start callback is invoked for each tool."""

    class QuickTool(BaseTool):
        @property
        def name(self) -> str:
            return "quick_tool"

        @property
        def description(self) -> str:
            return "Quick tool"

        def execute(self, params):
            return {"result": "Done"}

        def create_compact_output(self, full_result):
            return full_result

    # Setup
    tool = QuickTool()
    executor = AgentToolExecutor({"quick_tool": tool})

    # Track callback invocations
    callback_invocations = []

    def on_tool_start(name, input_data):
        callback_invocations.append((name, input_data))

    console = Console(file=StringIO())
    service = ToolExecutionService(executor, console=console, on_tool_start=on_tool_start)

    # Mock response data
    response_data = {
        "content": [
            {
                "type": "tool_use",
                "toolUse": [
                    {"id": "test-1", "name": "quick_tool", "input": {"key": "value"}}
                ]
            }
        ]
    }

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
    service.extract_and_execute(response_data, parser)

    # Verify callback was invoked
    assert len(callback_invocations) == 1
    assert callback_invocations[0][0] == "quick_tool"
    assert callback_invocations[0][1] == {"key": "value"}


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
