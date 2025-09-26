"""
Tool execution engine for Claude function calls.

This module handles the execution of tools that Claude requests during conversations,
including weather lookups, calculations, and time queries.
"""
from __future__ import annotations

import os
from datetime import datetime, UTC
from typing import Any, Dict, Optional


class ToolExecutor:
    """Executes tool calls requested by Claude."""

    def __init__(self, weather_api_key: Optional[str] = None):
        """
        Initialize the tool executor.

        Args:
            weather_api_key: OpenWeatherMap API key for weather lookups
        """
        self.weather_api_key = weather_api_key or os.getenv("OPENWEATHER_API_KEY")

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool call and return the result.

        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool call

        Returns:
            Dict containing the tool result with 'content' and optionally 'error'
        """
        try:
            if tool_name == "get_current_time":
                return self._get_current_time(parameters)
            else:
                return {
                    "error": f"Unknown tool: {tool_name}",
                    "content": f"Tool '{tool_name}' is not available."
                }
        except Exception as e:
            return {
                "error": str(e),
                "content": f"Error executing {tool_name}: {str(e)}"
            }

    def _get_current_time(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get current date and time."""
        timezone = params.get("timezone", "UTC")
        format_type = params.get("format", "human")

        try:
            # For simplicity, just use local time or UTC
            # A full implementation would use pytz for timezone handling
            if timezone.upper() == "UTC":
                now = datetime.now(UTC)
                tz_info = "UTC"
            else:
                now = datetime.now()
                tz_info = "local time"

            if format_type == "iso":
                time_str = now.isoformat()
            elif format_type == "unix":
                time_str = str(int(now.timestamp()))
            else:  # human format
                time_str = now.strftime("%Y-%m-%d %H:%M:%S")

            return {
                "content": f"Current time ({tz_info}): {time_str}",
                "timestamp": time_str,
                "timezone": tz_info
            }
        except Exception as e:
            return {
                "error": f"Time lookup failed: {str(e)}",
                "content": f"Could not get current time for timezone: {timezone}"
            }
