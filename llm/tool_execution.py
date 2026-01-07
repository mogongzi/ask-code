"""
Tool execution service.

Extracts and executes tool calls from LLM responses.
This eliminates duplication between streaming and blocking clients.
"""

from __future__ import annotations

import logging
from typing import Callable, List, Optional

from llm.types import ToolCall
from llm.parsers.base import ResponseParser
from tools.executor import ToolExecutor
from rich.console import Console

logger = logging.getLogger(__name__)


class ToolExecutionService:
    """Service for extracting and executing tool calls.

    This class encapsulates the logic for:
    1. Extracting tool calls from provider responses (using appropriate parser)
    2. Executing tools via ToolExecutor
    3. Collecting results into ToolCall objects

    This eliminates ~30 lines of duplicated code between streaming and blocking clients.
    """

    def __init__(
        self,
        tool_executor: Optional[ToolExecutor] = None,
        console: Optional[Console] = None,
        on_tool_start: Optional[Callable[[str, dict], None]] = None
    ):
        """Initialize tool execution service.

        Args:
            tool_executor: ToolExecutor instance for running tools.
                          If None, no tools will be executed.
            console: Rich console for UI output during tool execution.
            on_tool_start: Optional callback invoked when a tool starts executing.
                          Called with (tool_name, tool_input).
        """
        self.tool_executor = tool_executor
        self.console = console or Console()
        self._on_tool_start = on_tool_start

    def extract_and_execute(
        self,
        data: dict,
        parser: ResponseParser
    ) -> List[ToolCall]:
        """Extract tool calls from response and execute them.

        Args:
            data: Raw response data from provider
            parser: Parser for extracting tool calls from provider-specific format

        Returns:
            List of ToolCall objects with execution results

        Raises:
            ToolExecutionError: If tool execution fails critically
        """
        if not self.tool_executor:
            return []

        tool_calls_made = []

        try:
            # Extract tool call definitions using provider-specific parser
            raw_tool_calls = parser.extract_tool_calls(data)

            # Execute each tool
            for tool_call_dict in raw_tool_calls:
                tool_call = self._execute_single_tool(tool_call_dict)
                if tool_call:
                    tool_calls_made.append(tool_call)

        except Exception as e:
            logger.error(f"Error during tool execution: {e}", exc_info=True)
            # Don't raise - allow partial results
            # Clients can check if tool_calls list is incomplete

        return tool_calls_made

    def _execute_single_tool(self, tool_call_dict: dict) -> Optional[ToolCall]:
        """Execute a single tool call.

        Args:
            tool_call_dict: Tool call dictionary with id, name, input

        Returns:
            ToolCall with result, or None if execution failed
        """
        tool_id = tool_call_dict.get("id", "")
        tool_name = tool_call_dict.get("name", "")
        tool_input = tool_call_dict.get("input", {})

        logger.debug(f"Executing tool: {tool_name} with input: {tool_input}")

        # Notify callback for live Explored display
        if self._on_tool_start:
            try:
                self._on_tool_start(tool_name, tool_input)
            except Exception as e:
                logger.debug(f"on_tool_start callback error: {e}")

        tool_call: Optional[ToolCall] = None

        try:
            # Execute the tool
            result_data = self.tool_executor.execute_tool(tool_name, tool_input)

            # Extract result content (full version for LLM)
            result_content = result_data.get('content', '')
            # Extract display content (compact version for UI)
            display_content = result_data.get('display', '')

            if 'error' in result_data:
                logger.warning(f"Tool {tool_name} returned error: {result_data['error']}")
                result_content = f"Error: {result_data['error']}"
                display_content = result_content  # Same for errors

            # Create ToolCall object with both full and display results
            tool_call = ToolCall(
                id=tool_id,
                name=tool_name,
                input=tool_input,
                result=result_content,
                display_result=display_content
            )

        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {e}", exc_info=True)
            # Return ToolCall with error message as result
            error_msg = f"Tool execution failed: {str(e)}"
            tool_call = ToolCall(
                id=tool_id,
                name=tool_name,
                input=tool_input,
                result=error_msg,
                display_result=error_msg  # Same for errors
            )

        return tool_call

    def has_executor(self) -> bool:
        """Check if tool executor is available.

        Returns:
            True if executor is available, False otherwise
        """
        return self.tool_executor is not None
