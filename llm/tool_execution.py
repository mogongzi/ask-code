"""
Tool execution service.

Extracts and executes tool calls from LLM responses.
This eliminates duplication between streaming and blocking clients.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from llm.types import ToolCall
from llm.parsers.base import ResponseParser
from llm.exceptions import ToolExecutionError
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

    def __init__(self, tool_executor: Optional[ToolExecutor] = None, console: Optional[Console] = None):
        """Initialize tool execution service.

        Args:
            tool_executor: ToolExecutor instance for running tools.
                          If None, no tools will be executed.
            console: Rich console for UI output during tool execution.
        """
        self.tool_executor = tool_executor
        self.console = console or Console()

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

        # Display "Using tool..." message BEFORE execution starts
        self.console.print(f"[yellow]⚙ Using {tool_name} tool...[/yellow]")

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
                # Display error
                self.console.print(f"[red]✗ {display_content}[/red]")
            else:
                # Display success with compact result
                if display_content:
                    self.console.print(f"[green]✓ {display_content}[/green]")

            # Create ToolCall object with both full and display results
            return ToolCall(
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
            # Display exception error
            self.console.print(f"[red]✗ {error_msg}[/red]")
            return ToolCall(
                id=tool_id,
                name=tool_name,
                input=tool_input,
                result=error_msg,
                display_result=error_msg  # Same for errors
            )

    def has_executor(self) -> bool:
        """Check if tool executor is available.

        Returns:
            True if executor is available, False otherwise
        """
        return self.tool_executor is not None