"""
AgentToolExecutor bridges provider-managed tool calls to the agent's tool set.

This mirrors the interface expected by StreamingClient: a synchronous
`execute_tool(name, parameters)` that returns a dict with 'content' and
optional 'error'. Internally it runs the agent tools' async execute methods
in a dedicated event loop to avoid interfering with any running loop.
"""
from __future__ import annotations

import asyncio
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

        async def _run() -> Any:
            try:
                return await tool.execute(parameters or {})
            except Exception as e:  # pragma: no cover
                return f"Error executing {tool_name}: {e}"

        # Run the coroutine safely whether or not an event loop is already running
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if running_loop and running_loop.is_running():
            # Execute in a separate thread with its own loop
            import threading

            result_box: Dict[str, Any] = {}

            def _worker():
                loop = asyncio.new_event_loop()
                try:
                    asyncio.set_event_loop(loop)
                    result_box["value"] = loop.run_until_complete(_run())
                finally:
                    try:
                        loop.close()
                    finally:
                        asyncio.set_event_loop(None)

            t = threading.Thread(target=_worker, daemon=True)
            t.start()
            t.join()
            result = result_box.get("value")
        else:
            # No running loop in this thread; create one and run normally
            result = asyncio.run(_run())

        # Normalize to the expected dict shape with 'content'
        try:
            content = tool.format_result(result)
        except Exception:
            content = str(result)

        return {"content": content}
