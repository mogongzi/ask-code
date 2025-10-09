"""
Test that tool execution messages are displayed BEFORE tool execution.

This ensures users see "⚙ Using tool..." immediately, not after the tool completes.
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


def test_tool_message_displayed_before_execution():
    """Verify that 'Using tool...' message appears before tool completes."""
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

    # Verify the output contains both messages
    assert "Using slow_tool tool" in console_output, "Should show 'Using tool...' message"
    assert "Done" in console_output, "Should show completion message"

    # The key test: messages appear in correct order
    using_index = console_output.find("Using slow_tool tool")
    done_index = console_output.find("Done")

    assert using_index >= 0, "Should find 'Using tool...' message"
    assert done_index >= 0, "Should find 'Done' message"
    assert using_index < done_index, "'Using tool...' should appear BEFORE 'Done'"

    # Verify we got a ToolCall result
    assert len(tool_calls) == 1
    assert tool_calls[0].name == "slow_tool"


def test_multiple_tools_display_sequentially():
    """Verify that multiple tools display messages in order."""

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

    # Find message positions
    tool1_using = console_output.find("Using tool_1 tool")
    tool1_result = console_output.find("Result from tool_1")
    tool2_using = console_output.find("Using tool_2 tool")
    tool2_result = console_output.find("Result from tool_2")

    # Verify order: tool1 using -> tool1 result -> tool2 using -> tool2 result
    assert tool1_using >= 0, "Should show tool_1 using"
    assert tool1_result >= 0, "Should show tool_1 result"
    assert tool2_using >= 0, "Should show tool_2 using"
    assert tool2_result >= 0, "Should show tool_2 result"

    assert tool1_using < tool1_result, "tool_1 using should come before result"
    assert tool1_result < tool2_using, "tool_1 result should come before tool_2 using"
    assert tool2_using < tool2_result, "tool_2 using should come before result"

    # Verify both tools executed
    assert len(tool_calls) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
