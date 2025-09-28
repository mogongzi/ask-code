"""
Custom exceptions for Rails ReAct agent.

This module defines the exception hierarchy for better error handling
and recovery in the Rails analysis system.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AgentError(Exception):
    """Base exception for all agent-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        Initialize agent error.

        Args:
            message: Error message
            details: Additional error details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary representation."""
        return {
            'error_type': self.__class__.__name__,
            'message': self.message,
            'details': self.details,
        }


class ToolError(AgentError):
    """Base exception for tool-related errors."""

    def __init__(self, message: str, tool_name: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize tool error.

        Args:
            message: Error message
            tool_name: Name of the tool that failed
            details: Additional error details
        """
        super().__init__(message, details)
        self.tool_name = tool_name


class ToolInitializationError(ToolError):
    """Exception raised when tool initialization fails."""

    def __init__(self, tool_name: str, original_error: Exception,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize tool initialization error.

        Args:
            tool_name: Name of the tool that failed to initialize
            original_error: The original exception
            details: Additional error details
        """
        message = f"Failed to initialize tool '{tool_name}': {original_error}"
        super().__init__(message, tool_name, details)
        self.original_error = original_error


class ToolExecutionError(ToolError):
    """Exception raised when tool execution fails."""

    def __init__(self, tool_name: str, input_params: Dict[str, Any],
                 original_error: Exception, details: Optional[Dict[str, Any]] = None):
        """
        Initialize tool execution error.

        Args:
            tool_name: Name of the tool that failed
            input_params: Input parameters that caused the failure
            original_error: The original exception
            details: Additional error details
        """
        message = f"Tool '{tool_name}' execution failed: {original_error}"
        super().__init__(message, tool_name, details)
        self.input_params = input_params
        self.original_error = original_error


class ToolNotFoundError(ToolError):
    """Exception raised when a requested tool is not found."""

    def __init__(self, tool_name: str, available_tools: List[str]):
        """
        Initialize tool not found error.

        Args:
            tool_name: Name of the requested tool
            available_tools: List of available tool names
        """
        message = f"Tool '{tool_name}' not found. Available tools: {', '.join(available_tools)}"
        super().__init__(message, tool_name)
        self.available_tools = available_tools


class LLMError(AgentError):
    """Base exception for LLM-related errors."""

    def __init__(self, message: str, provider: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM error.

        Args:
            message: Error message
            provider: LLM provider name
            details: Additional error details
        """
        super().__init__(message, details)
        self.provider = provider


class LLMCommunicationError(LLMError):
    """Exception raised when LLM communication fails."""

    def __init__(self, provider: str, original_error: Exception,
                 retry_count: int = 0, details: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM communication error.

        Args:
            provider: LLM provider name
            original_error: The original exception
            retry_count: Number of retries attempted
            details: Additional error details
        """
        message = f"LLM communication failed with {provider} after {retry_count} retries: {original_error}"
        super().__init__(message, provider, details)
        self.original_error = original_error
        self.retry_count = retry_count


class LLMTimeoutError(LLMError):
    """Exception raised when LLM request times out."""

    def __init__(self, provider: str, timeout_seconds: float,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize LLM timeout error.

        Args:
            provider: LLM provider name
            timeout_seconds: Timeout duration in seconds
            details: Additional error details
        """
        message = f"LLM request to {provider} timed out after {timeout_seconds} seconds"
        super().__init__(message, provider, details)
        self.timeout_seconds = timeout_seconds


class ReActError(AgentError):
    """Base exception for ReAct loop errors."""

    def __init__(self, message: str, step: Optional[int] = None,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize ReAct error.

        Args:
            message: Error message
            step: Step number where error occurred
            details: Additional error details
        """
        super().__init__(message, details)
        self.step = step


class ReActMaxStepsError(ReActError):
    """Exception raised when ReAct loop reaches maximum steps."""

    def __init__(self, max_steps: int, current_step: int,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize ReAct max steps error.

        Args:
            max_steps: Maximum allowed steps
            current_step: Current step number
            details: Additional error details
        """
        message = f"ReAct loop reached maximum steps ({max_steps}) at step {current_step}"
        super().__init__(message, current_step, details)
        self.max_steps = max_steps


class ReActLoopError(ReActError):
    """Exception raised when ReAct loop gets stuck."""

    def __init__(self, step: int, loop_pattern: str,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize ReAct loop error.

        Args:
            step: Step number where loop was detected
            loop_pattern: Description of the loop pattern
            details: Additional error details
        """
        message = f"ReAct loop detected at step {step}: {loop_pattern}"
        super().__init__(message, step, details)
        self.loop_pattern = loop_pattern


class ConfigurationError(AgentError):
    """Exception raised for configuration-related errors."""

    def __init__(self, parameter: str, value: Any, reason: str,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize configuration error.

        Args:
            parameter: Configuration parameter name
            value: Invalid value
            reason: Reason why the value is invalid
            details: Additional error details
        """
        message = f"Invalid configuration for '{parameter}' = {value}: {reason}"
        super().__init__(message, details)
        self.parameter = parameter
        self.value = value
        self.reason = reason


class ProjectError(AgentError):
    """Exception raised for project-related errors."""

    def __init__(self, project_root: str, reason: str,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize project error.

        Args:
            project_root: Project root directory
            reason: Reason for the error
            details: Additional error details
        """
        message = f"Project error for '{project_root}': {reason}"
        super().__init__(message, details)
        self.project_root = project_root
        self.reason = reason


class ProjectNotFoundError(ProjectError):
    """Exception raised when project directory is not found."""

    def __init__(self, project_root: str):
        """
        Initialize project not found error.

        Args:
            project_root: Project root directory that was not found
        """
        super().__init__(project_root, "Directory does not exist")


class ProjectNotRailsError(ProjectError):
    """Exception raised when project is not a Rails project."""

    def __init__(self, project_root: str, missing_indicators: List[str]):
        """
        Initialize project not Rails error.

        Args:
            project_root: Project root directory
            missing_indicators: List of missing Rails indicators
        """
        reason = f"Not a Rails project (missing: {', '.join(missing_indicators)})"
        super().__init__(project_root, reason)
        self.missing_indicators = missing_indicators


# Exception recovery strategies
class ErrorRecoveryStrategy:
    """Base class for error recovery strategies."""

    def can_recover(self, error: AgentError) -> bool:
        """
        Check if this strategy can recover from the error.

        Args:
            error: The error to potentially recover from

        Returns:
            True if recovery is possible, False otherwise
        """
        return False

    def recover(self, error: AgentError) -> Any:
        """
        Attempt to recover from the error.

        Args:
            error: The error to recover from

        Returns:
            Recovery result or raises if recovery fails
        """
        raise NotImplementedError("Subclasses must implement recover method")


class ToolRetryStrategy(ErrorRecoveryStrategy):
    """Recovery strategy for retryable tool errors."""

    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.5):
        """
        Initialize tool retry strategy.

        Args:
            max_retries: Maximum number of retries
            backoff_factor: Backoff multiplier for retry delays
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def can_recover(self, error: AgentError) -> bool:
        """Check if error is retryable."""
        return isinstance(error, (ToolExecutionError, LLMCommunicationError))

    def recover(self, error: AgentError) -> Any:
        """Attempt recovery through retries."""
        # This would be implemented with actual retry logic
        # For now, just re-raise the error
        raise error


class FallbackToolStrategy(ErrorRecoveryStrategy):
    """Recovery strategy using fallback tools."""

    def __init__(self, fallback_mapping: Dict[str, List[str]]):
        """
        Initialize fallback tool strategy.

        Args:
            fallback_mapping: Mapping of tool names to fallback alternatives
        """
        self.fallback_mapping = fallback_mapping

    def can_recover(self, error: AgentError) -> bool:
        """Check if we have fallback tools."""
        if isinstance(error, ToolError) and error.tool_name:
            return error.tool_name in self.fallback_mapping
        return False

    def recover(self, error: AgentError) -> Any:
        """Suggest fallback tools."""
        if isinstance(error, ToolError) and error.tool_name:
            fallbacks = self.fallback_mapping.get(error.tool_name, [])
            return {"suggested_fallbacks": fallbacks}
        raise error