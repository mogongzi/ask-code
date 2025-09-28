"""
Structured logging for Rails ReAct agent.

This module provides centralized logging with structured output,
performance metrics, and debugging capabilities.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional
from contextlib import contextmanager
from dataclasses import dataclass, asdict

from rich.console import Console
from rich.logging import RichHandler


@dataclass
class LogContext:
    """Context information for structured logging."""
    session_id: Optional[str] = None
    user_query: Optional[str] = None
    project_root: Optional[str] = None
    step_number: Optional[int] = None
    tool_name: Optional[str] = None


class StructuredLogger:
    """Structured logger with Rich console integration."""

    def __init__(self, name: str, level: str = "INFO", console: Optional[Console] = None):
        """
        Initialize structured logger.

        Args:
            name: Logger name
            level: Logging level
            console: Rich console for output
        """
        self.name = name
        self.console = console or Console()
        self.context = LogContext()

        # Set up Python logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        # Clear existing handlers
        self.logger.handlers.clear()

        # Add Rich handler for console output
        rich_handler = RichHandler(
            console=self.console,
            show_time=True,
            show_path=False,
            rich_tracebacks=True
        )
        rich_handler.setFormatter(logging.Formatter(
            fmt="%(message)s",
            datefmt="[%X]"
        ))
        self.logger.addHandler(rich_handler)

        # Performance tracking
        self._operation_start_times: Dict[str, float] = {}

    def set_context(self, **kwargs) -> None:
        """
        Set logging context.

        Args:
            **kwargs: Context variables to set
        """
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)

    def clear_context(self) -> None:
        """Clear logging context."""
        self.context = LogContext()

    def _format_message(self, message: str, extra: Optional[Dict[str, Any]] = None) -> str:
        """Format message with context and extra data."""
        parts = []

        # Add context prefixes
        if self.context.step_number:
            parts.append(f"[Step {self.context.step_number}]")

        if self.context.tool_name:
            parts.append(f"[{self.context.tool_name}]")

        # Add main message
        parts.append(message)

        formatted = " ".join(parts)

        # Add extra data as JSON if provided
        if extra:
            formatted += f" | {json.dumps(extra, default=str)}"

        return formatted

    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log debug message."""
        formatted = self._format_message(message, extra)
        self.logger.debug(formatted)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log info message."""
        formatted = self._format_message(message, extra)
        self.logger.info(formatted)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """Log warning message."""
        formatted = self._format_message(message, extra)
        self.logger.warning(formatted)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None,
              exc_info: bool = False) -> None:
        """Log error message."""
        formatted = self._format_message(message, extra)
        self.logger.error(formatted, exc_info=exc_info)

    def critical(self, message: str, extra: Optional[Dict[str, Any]] = None,
                exc_info: bool = False) -> None:
        """Log critical message."""
        formatted = self._format_message(message, extra)
        self.logger.critical(formatted, exc_info=exc_info)

    @contextmanager
    def operation(self, operation_name: str, extra: Optional[Dict[str, Any]] = None):
        """
        Context manager for timing operations.

        Args:
            operation_name: Name of the operation
            extra: Additional data to log
        """
        start_time = time.time()
        self._operation_start_times[operation_name] = start_time

        self.debug(f"Starting operation: {operation_name}", extra)

        try:
            yield
            duration = time.time() - start_time
            self.info(
                f"Completed operation: {operation_name}",
                {"duration_ms": round(duration * 1000, 2), **(extra or {})}
            )
        except Exception as e:
            duration = time.time() - start_time
            self.error(
                f"Failed operation: {operation_name}",
                {
                    "duration_ms": round(duration * 1000, 2),
                    "error": str(e),
                    "error_type": type(e).__name__,
                    **(extra or {})
                },
                exc_info=True
            )
            raise
        finally:
            self._operation_start_times.pop(operation_name, None)

    def log_tool_execution(self, tool_name: str, input_params: Dict[str, Any],
                          success: bool, duration_ms: float,
                          result_summary: Optional[str] = None,
                          error: Optional[str] = None) -> None:
        """
        Log tool execution details.

        Args:
            tool_name: Name of the executed tool
            input_params: Input parameters
            success: Whether execution succeeded
            duration_ms: Execution duration in milliseconds
            result_summary: Summary of results
            error: Error message if failed
        """
        log_data = {
            "tool_name": tool_name,
            "input_params": input_params,
            "success": success,
            "duration_ms": round(duration_ms, 2),
            "result_summary": result_summary,
        }

        if success:
            self.info(f"Tool execution successful: {tool_name}", log_data)
        else:
            log_data["error"] = error
            self.error(f"Tool execution failed: {tool_name}", log_data)

    def log_react_step(self, step_type: str, step_number: int,
                      content: str, tool_name: Optional[str] = None) -> None:
        """
        Log ReAct step details.

        Args:
            step_type: Type of step (thought, action, observation, answer)
            step_number: Step number
            content: Step content
            tool_name: Tool name if applicable
        """
        log_data = {
            "step_type": step_type,
            "step_number": step_number,
            "content_length": len(content),
            "tool_name": tool_name,
        }

        self.info(f"ReAct step: {step_type}", log_data)

    def log_llm_interaction(self, provider: str, tokens_used: int, cost: float,
                           response_length: int, tools_called: int,
                           duration_ms: float) -> None:
        """
        Log LLM interaction details.

        Args:
            provider: LLM provider name
            tokens_used: Number of tokens used
            cost: Cost of the interaction
            response_length: Length of the response
            tools_called: Number of tools called
            duration_ms: Duration in milliseconds
        """
        log_data = {
            "provider": provider,
            "tokens_used": tokens_used,
            "cost": round(cost, 4),
            "response_length": response_length,
            "tools_called": tools_called,
            "duration_ms": round(duration_ms, 2),
        }

        self.info("LLM interaction completed", log_data)

    def print_status(self, message: str, status: str = "info") -> None:
        """
        Print status message to console with Rich formatting.

        Args:
            message: Status message
            status: Status type (info, success, warning, error)
        """
        if status == "success":
            self.console.print(f"[green]✓ {message}[/green]")
        elif status == "warning":
            self.console.print(f"[yellow]⚠ {message}[/yellow]")
        elif status == "error":
            self.console.print(f"[red]✗ {message}[/red]")
        elif status == "working":
            self.console.print(f"[blue]⚙ {message}[/blue]")
        else:
            self.console.print(f"[dim]• {message}[/dim]")

    def print_summary(self, title: str, data: Dict[str, Any]) -> None:
        """
        Print formatted summary to console.

        Args:
            title: Summary title
            data: Summary data
        """
        self.console.print(f"\n[bold]{title}[/bold]")
        for key, value in data.items():
            self.console.print(f"  {key}: {value}")


class AgentLogger:
    """Centralized logger for the Rails ReAct agent."""

    _instance: Optional[StructuredLogger] = None

    @classmethod
    def get_logger(cls, name: str = "rails_agent", level: str = "INFO",
                  console: Optional[Console] = None) -> StructuredLogger:
        """
        Get or create the global agent logger.

        Args:
            name: Logger name
            level: Logging level
            console: Rich console

        Returns:
            StructuredLogger instance
        """
        if cls._instance is None:
            cls._instance = StructuredLogger(name, level, console)
        return cls._instance

    @classmethod
    def configure(cls, level: str = "INFO", console: Optional[Console] = None) -> None:
        """
        Configure the global agent logger.

        Args:
            level: Logging level
            console: Rich console
        """
        if cls._instance:
            cls._instance.logger.setLevel(getattr(logging, level.upper()))
        else:
            cls._instance = StructuredLogger("rails_agent", level, console)

    @classmethod
    def set_context(cls, **kwargs) -> None:
        """Set logging context on the global logger."""
        if cls._instance:
            cls._instance.set_context(**kwargs)

    @classmethod
    def clear_context(cls) -> None:
        """Clear logging context on the global logger."""
        if cls._instance:
            cls._instance.clear_context()


# Convenience functions for common logging patterns
def log_agent_start(user_query: str, project_root: Optional[str] = None) -> None:
    """Log agent startup."""
    logger = AgentLogger.get_logger()
    logger.set_context(user_query=user_query, project_root=project_root)
    logger.info("Rails ReAct agent started", {
        "query_length": len(user_query),
        "project_root": project_root
    })


def log_agent_complete(duration_ms: float, steps_completed: int,
                      tools_used: int, success: bool) -> None:
    """Log agent completion."""
    logger = AgentLogger.get_logger()
    logger.info("Rails ReAct agent completed", {
        "duration_ms": round(duration_ms, 2),
        "steps_completed": steps_completed,
        "tools_used": tools_used,
        "success": success
    })
    logger.clear_context()


def log_error_with_recovery(error: Exception, recovery_attempted: bool,
                           recovery_successful: bool = False) -> None:
    """Log error with recovery information."""
    logger = AgentLogger.get_logger()
    logger.error("Agent error occurred", {
        "error": str(error),
        "error_type": type(error).__name__,
        "recovery_attempted": recovery_attempted,
        "recovery_successful": recovery_successful
    }, exc_info=True)