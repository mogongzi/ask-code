"""
Base LLM client with Template Method pattern.

Provides common functionality for all LLM clients (streaming and blocking),
reducing code duplication and enforcing consistent behavior.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Optional

from llm.types import LLMResponse, Provider, ToolCall
from llm.parsers import ParserRegistry, ResponseParser
from llm.tool_execution import ToolExecutionService
from llm.error_handling import ErrorHandler, with_error_handling
from tools.executor import ToolExecutor
from rich.console import Console

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients.

    Implements the Template Method pattern:
    - send_message() is the template method defining the algorithm
    - Subclasses implement specific steps (_make_request, _build_response)

    This eliminates duplication between streaming and blocking clients.
    """

    def __init__(
        self,
        tool_executor: Optional[ToolExecutor] = None,
        console: Optional[Console] = None,
        provider: Provider = Provider.BEDROCK
    ):
        """Initialize base client.

        Args:
            tool_executor: Optional tool executor for function calling
            console: Rich console for output
            provider: Provider type (determines parser to use)
        """
        self.provider = provider
        self.parser = ParserRegistry.get_parser(provider)
        self.console = console or Console()
        self.tool_service = ToolExecutionService(tool_executor, console=self.console)
        self._abort = False

    def abort(self) -> None:
        """Signal the current request to abort.

        Subclasses should check self._abort during long operations.
        """
        self._abort = True

    # Template Method
    def send_message(
        self,
        url: str,
        payload: dict,
        **kwargs
    ) -> LLMResponse:
        """Send message to LLM (Template Method).

        This method defines the algorithm:
        1. Make request (subclass-specific)
        2. Parse response (using parser)
        3. Execute tools (if any)
        4. Build final response

        Subclasses implement _make_request() and optionally override other steps.

        Args:
            url: Endpoint URL
            payload: Request payload
            **kwargs: Additional provider-specific arguments

        Returns:
            LLMResponse with results

        Raises:
            LLMError: On various failure conditions
        """
        # Reset abort flag
        self._abort = False

        try:
            # Step 1: Make the request (subclass-specific)
            response_data = self._make_request(url, payload, **kwargs)

            # Check for abort
            if self._abort:
                return LLMResponse.aborted_response()

            # Step 2: Parse the response using provider-specific parser
            text = self.parser.extract_text(response_data)
            model_name = self.parser.extract_model_name(response_data)
            usage = self.parser.extract_usage(response_data)

            # Step 3: Execute tools (if any)
            tool_calls = self.tool_service.extract_and_execute(
                response_data,
                self.parser
            )

            # Step 4: Build final response
            return LLMResponse(
                text=text,
                tokens=usage.total_tokens,
                cost=usage.cost,
                tool_calls=tool_calls,
                model_name=model_name,
                aborted=self._abort
            )

        except Exception as e:
            # Centralized error handling
            return ErrorHandler.handle_exception(e)

    @abstractmethod
    def _make_request(
        self,
        url: str,
        payload: dict,
        **kwargs
    ) -> dict:
        """Make the actual HTTP request.

        This is the primitive operation that subclasses must implement.

        Args:
            url: Endpoint URL
            payload: Request payload
            **kwargs: Additional arguments

        Returns:
            Raw response data as dict

        Raises:
            Various exceptions (handled by template method)
        """
        ...

    # Helper methods that subclasses can use

    def _get_parser(self) -> ResponseParser:
        """Get the current parser instance.

        Returns:
            ResponseParser for current provider
        """
        return self.parser

    def _has_tools(self) -> bool:
        """Check if tool executor is available.

        Returns:
            True if tools can be executed
        """
        return self.tool_service.has_executor()

    def _check_abort(self) -> bool:
        """Check if abort was requested.

        Returns:
            True if abort requested
        """
        return self._abort

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"provider={self.provider.value}, "
            f"has_tools={self._has_tools()})"
        )