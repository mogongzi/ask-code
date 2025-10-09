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

        # Execute tool with debug logging if debug is enabled
        try:
            if tool.debug_enabled:
                full_result = tool.execute_with_debug(parameters or {})
                # In verbose mode, use full result for both display and LLM
                compact_result = full_result
            else:
                full_result = tool.execute(parameters or {})
                # Create compact version for UI display
                compact_result = tool.create_compact_output(full_result)
        except Exception as e:  # pragma: no cover
            full_result = f"Error executing {tool_name}: {e}"
            compact_result = full_result

        # Format both versions
        try:
            full_content = tool.format_result(full_result)
            display_content = tool.format_result(compact_result)
        except Exception:
            full_content = str(full_result)
            display_content = str(compact_result)

        # Return both versions: full for LLM context, display for UI
        return {
            "content": full_content,  # Full result for LLM conversation
            "display": display_content  # Compact result for UI display
        }
