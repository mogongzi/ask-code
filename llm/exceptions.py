"""
Exception hierarchy for LLM client operations.

Provides specific exception types for different failure modes,
making error handling more precise and testable.
"""

from __future__ import annotations

from typing import Optional


class LLMError(Exception):
    """Base exception for all LLM client errors.

    All LLM-related exceptions should inherit from this to allow
    for broad exception handling when needed.
    """

    def __init__(self, message: str, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.original_error = original_error


class LLMTimeoutError(LLMError):
    """Request timed out waiting for LLM response.

    Raised when the request exceeds the configured timeout period.
    """

    def __init__(self, message: str = "Request timed out", timeout: float = 0.0, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)
        self.timeout = timeout


class LLMNetworkError(LLMError):
    """Network-related error occurred during LLM request.

    Raised for connection errors, DNS failures, etc.
    """

    def __init__(self, message: str = "Network error", original_error: Optional[Exception] = None):
        super().__init__(message, original_error)


class LLMResponseError(LLMError):
    """LLM returned an error response.

    Raised when the LLM API returns an error (4xx, 5xx status codes).
    """

    def __init__(self, message: str, status_code: Optional[int] = None, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)
        self.status_code = status_code


class LLMParsingError(LLMError):
    """Failed to parse LLM response.

    Raised when response format is unexpected or malformed.
    """

    def __init__(self, message: str, provider: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)
        self.provider = provider


class ToolExecutionError(LLMError):
    """Tool execution failed during LLM response processing.

    Raised when a tool called by the LLM fails to execute properly.
    """

    def __init__(self, message: str, tool_name: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message, original_error)
        self.tool_name = tool_name


class LLMAbortedError(LLMError):
    """Request was aborted by user.

    Raised when the user cancels an in-progress LLM request.
    """

    def __init__(self, message: str = "Request aborted by user"):
        super().__init__(message)