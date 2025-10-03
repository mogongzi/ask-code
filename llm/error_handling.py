"""
Error handling infrastructure for LLM clients.

Provides centralized error handling to eliminate duplicate error handling code
across streaming and blocking clients.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Optional, TypeVar, cast
from requests.exceptions import ReadTimeout, ConnectTimeout, RequestException

from llm.types import LLMResponse, ToolCall
from llm.exceptions import LLMTimeoutError, LLMNetworkError, LLMError

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorHandler:
    """Centralized error handler for LLM client operations.

    Converts various exception types into appropriate LLMResponse objects
    with error information. This eliminates the need for duplicate error
    handling code in each client.
    """

    @staticmethod
    def handle_timeout(
        error: Exception,
        partial_text: str = "",
        partial_tools: Optional[list[ToolCall]] = None
    ) -> LLMResponse:
        """Handle timeout errors.

        Args:
            error: The timeout exception
            partial_text: Any text received before timeout
            partial_tools: Any tool calls completed before timeout

        Returns:
            LLMResponse with error set
        """
        error_message = f"Request timed out: {error}"
        logger.error(error_message)

        return LLMResponse(
            text=partial_text,
            tokens=0,
            cost=0.0,
            tool_calls=partial_tools or [],
            error=error_message
        )

    @staticmethod
    def handle_network(
        error: Exception,
        partial_text: str = "",
        partial_tools: Optional[list[ToolCall]] = None
    ) -> LLMResponse:
        """Handle network errors.

        Args:
            error: The network exception
            partial_text: Any text received before error
            partial_tools: Any tool calls completed before error

        Returns:
            LLMResponse with error set
        """
        error_message = f"Network error: {error}"
        logger.error(error_message)

        return LLMResponse(
            text=partial_text,
            tokens=0,
            cost=0.0,
            tool_calls=partial_tools or [],
            error=error_message
        )

    @staticmethod
    def handle_generic(
        error: Exception,
        partial_text: str = "",
        partial_tools: Optional[list[ToolCall]] = None
    ) -> LLMResponse:
        """Handle generic/unexpected errors.

        Args:
            error: The exception
            partial_text: Any text received before error
            partial_tools: Any tool calls completed before error

        Returns:
            LLMResponse with error set
        """
        error_message = f"Unexpected error: {error}"
        logger.error(error_message, exc_info=True)

        return LLMResponse(
            text=partial_text,
            tokens=0,
            cost=0.0,
            tool_calls=partial_tools or [],
            error=error_message
        )

    @classmethod
    def handle_exception(
        cls,
        error: Exception,
        partial_text: str = "",
        partial_tools: Optional[list[ToolCall]] = None
    ) -> LLMResponse:
        """Handle any exception and return appropriate LLMResponse.

        This is the main entry point for error handling.

        Args:
            error: The exception to handle
            partial_text: Any text received before error
            partial_tools: Any tool calls completed before error

        Returns:
            LLMResponse with error set
        """
        if isinstance(error, (ReadTimeout, ConnectTimeout)):
            return cls.handle_timeout(error, partial_text, partial_tools)
        elif isinstance(error, RequestException):
            return cls.handle_network(error, partial_text, partial_tools)
        else:
            return cls.handle_generic(error, partial_text, partial_tools)


def with_error_handling(func: Callable[..., LLMResponse]) -> Callable[..., LLMResponse]:
    """Decorator that adds standardized error handling to LLM client methods.

    Catches common exceptions and converts them to LLMResponse with error set.
    This eliminates the need for try/except blocks in every client method.

    Usage:
        @with_error_handling
        def send_message(self, ...) -> LLMResponse:
            # Just implement happy path - errors handled automatically
            ...

    Args:
        func: Function that returns LLMResponse

    Returns:
        Wrapped function with error handling
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> LLMResponse:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return ErrorHandler.handle_exception(e)

    return cast(Callable[..., LLMResponse], wrapper)