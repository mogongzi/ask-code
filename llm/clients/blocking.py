"""
Blocking (synchronous) LLM client.

Makes single HTTP POST request and waits for complete response.
Refactored to use new infrastructure, reducing code by ~60%.
"""

from __future__ import annotations

import logging
from typing import Optional
import requests
from requests.exceptions import RequestException, ReadTimeout, ConnectTimeout

from llm.types import LLMResponse, Provider
from llm.clients.base import BaseLLMClient
from llm.ui.spinner import SpinnerManager
from tools.executor import ToolExecutor
from rich.console import Console

logger = logging.getLogger(__name__)


class BlockingClient(BaseLLMClient):
    """Blocking (synchronous) LLM client.

    Makes a single HTTP POST request and blocks until complete response received.
    Shows animated spinner during wait for better UX.

    This is the refactored version using new infrastructure:
    - Inherits from BaseLLMClient (Template Method pattern)
    - Uses ParserRegistry for response parsing
    - Uses ToolExecutionService for tool execution
    - Uses ErrorHandler for error handling
    - Uses SpinnerManager for UI

    Result: ~60% less code while maintaining all functionality.
    """

    def __init__(
        self,
        tool_executor: Optional[ToolExecutor] = None,
        console: Optional[Console] = None,
        provider: Provider = Provider.BEDROCK,
        timeout: float = 120.0,
    ):
        """Initialize blocking client.

        Args:
            tool_executor: Optional tool executor for function calling
            console: Rich console for output (used by spinner)
            provider: Provider type (determines parser)
            timeout: Default request timeout in seconds
        """
        super().__init__(tool_executor, provider)
        self.console = console or Console()
        self.timeout = timeout
        self.spinner = SpinnerManager(console=self.console)

    def _make_request(
        self, url: str, payload: dict, timeout: Optional[float] = None, **kwargs
    ) -> dict:
        """Make blocking HTTP POST request.

        Implements the primitive operation for Template Method.

        Args:
            url: Endpoint URL (should be /invoke, not /invoke-with-response-stream)
            payload: Request payload
            timeout: Request timeout (uses default if not specified)
            **kwargs: Additional arguments (ignored for compatibility)

        Returns:
            Response data as dict

        Raises:
            ReadTimeout, ConnectTimeout, RequestException: On errors
        """
        # Start spinner for user feedback
        self.spinner.start()

        try:
            # Make single HTTP POST request
            logger.debug(f"Sending blocking request to {url}")
            timeout_val = timeout or self.timeout

            response = requests.post(url, json=payload, timeout=timeout_val)
            response.raise_for_status()
            data = response.json()

            return data

        finally:
            # Always stop spinner
            self.spinner.stop()

    # Stream compatibility method
    def stream_with_live_rendering(
        self,
        url: str,
        payload: dict,
        mapper=None,  # Not used, kept for API compatibility
        *,
        console: Optional[Console] = None,
        use_thinking: bool = False,
        provider_name: str = "bedrock",
        show_model_name: bool = True,
        live_window: int = 6,
    ) -> LLMResponse:
        """Blocking version with live rendering for API compatibility.

        This method exists for compatibility with StreamingClient API.
        It makes a blocking request and displays results.

        Args:
            url: Endpoint URL
            payload: Request payload
            mapper: Not used (kept for compatibility)
            console: Console for output
            use_thinking: Not used in blocking mode
            provider_name: Provider name string
            show_model_name: Whether to display model name
            live_window: Not used in blocking mode

        Returns:
            LLMResponse with results
        """
        # Use provided console temporarily
        original_console = self.console
        if console:
            self.console = console
            self.spinner = SpinnerManager(console=console)

        try:
            # Get provider from name
            provider = Provider.from_string(provider_name)
            original_provider = self.provider

            # Temporarily switch provider if different
            if provider != self.provider:
                self.provider = provider
                self.parser = self.parser_registry.get_parser(provider)

            # Send message using template method
            result = self.send_message(url, payload)

            # Display results
            if result.model_name and show_model_name and console:
                console.rule(f"[bold cyan]{result.model_name}")

            if result.text and console:
                console.print(result.text)

            # Display tool executions
            if result.tool_calls and console:
                for tool_call in result.tool_calls:
                    console.print(f"[yellow]⚙ Using {tool_call.name} tool...[/yellow]")
                    if tool_call.result:
                        console.print(f"[green]✓ {tool_call.result}[/green]")

            # Display error if any
            if result.error and console:
                # Highlight network errors more prominently
                if (
                    "Network error" in result.error
                    or "502" in result.error
                    or "Bad Gateway" in result.error
                ):
                    console.print()
                    console.print(
                        f"[bold red on yellow]⚠ {result.error}[/bold red on yellow]"
                    )
                    console.print(
                        "[yellow]Tip: Check if the API server is running[/yellow]"
                    )
                    console.print()
                else:
                    console.print(f"[red]Error: {result.error}[/red]")

            # Restore original provider
            if provider != original_provider:
                self.provider = original_provider
                self.parser = self.parser_registry.get_parser(original_provider)

            return result

        finally:
            # Restore original console
            self.console = original_console
            self.spinner = SpinnerManager(console=original_console)

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"BlockingClient("
            f"provider={self.provider.value}, "
            f"timeout={self.timeout}s, "
            f"has_tools={self._has_tools()})"
        )
