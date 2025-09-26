"""
Base tool class for ReAct Rails agent tools.
"""
from __future__ import annotations

import os
import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from rich.console import Console


class BaseTool(ABC):
    """Abstract base class for all ReAct agent tools."""

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the tool.

        Args:
            project_root: Root directory of the Rails project
        """
        self.project_root = project_root
        self.console = Console()
        self.debug_enabled = os.getenv('AGENT_TOOL_DEBUG', '').lower() in ('1', 'true', 'yes')

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool name for identification."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what this tool does."""
        pass

    @property
    def parameters(self) -> Dict[str, Any]:
        """
        Tool parameter schema for LLM function calling.

        Returns:
            JSON schema describing the tool's input parameters
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    @abstractmethod
    async def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Execute the tool with given parameters.

        Args:
            input_params: Input parameters for tool execution

        Returns:
            Tool execution result
        """
        pass

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """
        Validate input parameters.

        Args:
            input_params: Parameters to validate

        Returns:
            True if valid, False otherwise
        """
        # Default implementation - override in subclasses for specific validation
        return isinstance(input_params, dict)

    def format_result(self, result: Any) -> str:
        """
        Format tool result for LLM consumption.

        Args:
            result: Raw tool result

        Returns:
            Formatted string result
        """
        if isinstance(result, str):
            return result
        elif isinstance(result, (list, dict)):
            return json.dumps(result, indent=2)
        else:
            return str(result)

    def _debug_log(self, message: str, data: Any = None) -> None:
        """Log debug information if debugging is enabled."""
        if self.debug_enabled:
            prefix = f"🔧 [{self.name}]"
            if data is not None:
                if isinstance(data, (dict, list)):
                    data_str = json.dumps(data, indent=2, default=str)[:2000]  # Truncate long data
                    if len(str(data)) > 2000:
                        data_str += "... [truncated]"
                else:
                    data_str = str(data)[:2000]
                    if len(str(data)) > 2000:
                        data_str += "... [truncated]"
                self.console.print(f"[dim cyan]{prefix} {message}[/dim cyan]")
                self.console.print(f"[dim]{data_str}[/dim]")
            else:
                self.console.print(f"[dim cyan]{prefix} {message}[/dim cyan]")

    def _debug_input(self, input_params: Dict[str, Any]) -> None:
        """Log input parameters for debugging."""
        self._debug_log("📥 INPUT", input_params)

    def _debug_output(self, result: Any, execution_time_ms: Optional[float] = None) -> None:
        """Log output result for debugging."""
        time_info = f" ({execution_time_ms:.1f}ms)" if execution_time_ms else ""
        if isinstance(result, dict) and "matches" in result:
            # Special handling for search results
            summary = {
                "total_matches": len(result.get("matches", [])),
                "first_match": result["matches"][0] if result.get("matches") else None,
                **{k: v for k, v in result.items() if k != "matches"}
            }
            self._debug_log(f"📤 OUTPUT{time_info}", summary)
        elif isinstance(result, dict) and "error" in result:
            self._debug_log(f"❌ ERROR{time_info}", result)
        else:
            self._debug_log(f"📤 OUTPUT{time_info}", result)

    async def execute_with_debug(self, input_params: Dict[str, Any]) -> Any:
        """Execute tool with debug logging wrapper."""
        import time

        self._debug_input(input_params)
        start_time = time.time()

        try:
            result = await self.execute(input_params)
            execution_time = (time.time() - start_time) * 1000
            self._debug_output(result, execution_time)
            return result
        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_result = {"error": str(e), "type": type(e).__name__}
            self._debug_output(error_result, execution_time)
            raise