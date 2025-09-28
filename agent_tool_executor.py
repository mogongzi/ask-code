"""
AgentToolExecutor bridges provider-managed tool calls to the agent's tool set.

This mirrors the interface expected by StreamingClient: a synchronous
`execute_tool(name, parameters)` that returns a dict with 'content' and
optional 'error'. Executes agent tools synchronously.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping

from tools.base_tool import BaseTool


class AgentToolExecutor:
    """Synchronous adapter to run agent tools for provider-managed tool calls."""

    def __init__(self, tools: Mapping[str, BaseTool]):
        self.tools = dict(tools or {})

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        tool = self.tools.get(tool_name)
        if not tool:
            return {
                "error": f"Unknown tool: {tool_name}",
                "content": f"Tool '{tool_name}' is not available."
            }

        # Execute tool synchronously (no more async/await)
        try:
            result = tool.execute(parameters or {})
        except Exception as e:  # pragma: no cover
            result = f"Error executing {tool_name}: {e}"

        # Normalize to the expected dict shape with 'content'
        try:
            content = tool.format_result(result)
        except Exception:
            content = str(result)

        return {"content": content}
