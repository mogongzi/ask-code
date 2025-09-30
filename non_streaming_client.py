"""NonStreamingClient for handling LLM non-streaming interactions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from requests.exceptions import RequestException, ReadTimeout, ConnectTimeout
import requests

from tools.executor import ToolExecutor
from streaming_client import StreamResult

logger = logging.getLogger(__name__)


class NonStreamingClient:
    """Handles non-streaming interactions with LLM providers."""

    def __init__(self, tool_executor: Optional[ToolExecutor] = None):
        self.tool_executor = tool_executor
        self._abort = False

    def abort(self) -> None:
        """Signal the current request to abort (no-op for non-streaming)."""
        self._abort = True

    def send_message(
        self,
        url: str,
        payload: dict,
        *,
        mapper=None,  # Not used in non-streaming, kept for API compatibility
        provider_name: str = "bedrock",
        timeout: float = 120.0
    ) -> StreamResult:
        """Send a message and receive a complete response.

        Args:
            url: The endpoint URL (should be /invoke, not /invoke-with-response-stream)
            payload: The request payload
            mapper: Not used, kept for compatibility with StreamingClient API
            provider_name: Name of the provider for specialized handling
            timeout: Request timeout in seconds

        Returns:
            StreamResult with complete response data
        """
        # Reset abort flag
        self._abort = False

        try:
            # Make single HTTP POST request
            logger.debug(f"Sending non-streaming request to {url}")
            response = requests.post(url, json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            # Extract text content
            text = self._extract_text(data, provider_name)

            # Extract model name
            model_name = self._extract_model_name(data, provider_name)

            # Extract and execute tool calls
            tool_calls_made = self._execute_tool_calls(data, provider_name)

            # Extract token usage and cost
            tokens, cost = self._extract_usage(data, provider_name)

            return StreamResult(
                text=text,
                tokens=tokens,
                cost=cost,
                tool_calls=tool_calls_made,
                model_name=model_name,
                aborted=self._abort
            )

        except (ReadTimeout, ConnectTimeout) as e:
            logger.error(f"Request timed out: {e}")
            return StreamResult(
                text="",
                tokens=0,
                cost=0.0,
                tool_calls=[],
                error=f"Request timed out: {e}"
            )
        except RequestException as e:
            logger.error(f"Network error: {e}")
            return StreamResult(
                text="",
                tokens=0,
                cost=0.0,
                tool_calls=[],
                error=f"Network error: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            return StreamResult(
                text="",
                tokens=0,
                cost=0.0,
                tool_calls=[],
                error=f"Unexpected error: {e}"
            )

    def _extract_text(self, data: dict, provider_name: str) -> str:
        """Extract text content from response data.

        Different providers have different response formats:
        - Bedrock: response['content'][0]['text'] (direct format from /invoke)
        - Azure/OpenAI: response['choices'][0]['message']['content']
        """
        try:
            if provider_name == "bedrock":
                # Bedrock format (direct from /invoke endpoint)
                content = data.get("content", [])
                if isinstance(content, list) and len(content) > 0:
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            return item.get("text", "")
                return ""
            elif provider_name in ["azure", "openai"]:
                # OpenAI/Azure format
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                # Generic fallback
                logger.warning(f"Unknown provider {provider_name}, using generic text extraction")
                return data.get("text", "") or data.get("content", "")
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return ""

    def _extract_model_name(self, data: dict, provider_name: str) -> Optional[str]:
        """Extract model name from response data."""
        try:
            if provider_name == "bedrock":
                # Bedrock format (direct from /invoke endpoint)
                return data.get("model", None)
            elif provider_name in ["azure", "openai"]:
                return data.get("model", None)
            else:
                return data.get("model", None)
        except Exception as e:
            logger.error(f"Error extracting model name: {e}")
            return None

    def _execute_tool_calls(self, data: dict, provider_name: str) -> List[dict]:
        """Extract tool calls from response and execute them.

        Returns list of tool call results in the format:
        [
            {
                "tool_call": {
                    "id": "tool_call_id",
                    "name": "tool_name",
                    "input": {...}
                },
                "result": "tool result text"
            },
            ...
        ]
        """
        if not self.tool_executor:
            return []

        tool_calls_made = []

        try:
            # Extract tool calls based on provider format
            tool_calls = self._extract_tool_calls(data, provider_name)

            # Execute each tool call
            for tool_call in tool_calls:
                tool_id = tool_call.get("id")
                tool_name = tool_call.get("name")
                tool_input = tool_call.get("input", {})

                logger.debug(f"Executing tool: {tool_name} with input: {tool_input}")

                # Execute the tool
                result = self.tool_executor.execute_tool(tool_name, tool_input)

                # Store tool call data
                tool_calls_made.append({
                    "tool_call": {
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_input
                    },
                    "result": result.get('content', '')
                })

        except Exception as e:
            logger.error(f"Error executing tool calls: {e}", exc_info=True)

        return tool_calls_made

    def _extract_tool_calls(self, data: dict, provider_name: str) -> List[dict]:
        """Extract tool calls from response data.

        Returns list of tool calls in standardized format:
        [
            {
                "id": "tool_call_id",
                "name": "tool_name",
                "input": {...}
            },
            ...
        ]
        """
        tool_calls = []

        try:
            if provider_name == "bedrock":
                # Bedrock format (direct from /invoke endpoint): content array with tool_use items
                content = data.get("content", [])
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_use":
                            tool_calls.append({
                                "id": item.get("id"),
                                "name": item.get("name"),
                                "input": item.get("input", {})
                            })

            elif provider_name in ["azure", "openai"]:
                # OpenAI/Azure format: message.tool_calls array
                message = data.get("choices", [{}])[0].get("message", {})
                raw_tool_calls = message.get("tool_calls", [])
                for tc in raw_tool_calls:
                    if isinstance(tc, dict):
                        function = tc.get("function", {})
                        # Parse function arguments if it's a JSON string
                        args = function.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}
                        tool_calls.append({
                            "id": tc.get("id"),
                            "name": function.get("name"),
                            "input": args
                        })

        except Exception as e:
            logger.error(f"Error extracting tool calls: {e}")

        return tool_calls

    def _extract_usage(self, data: dict, provider_name: str) -> tuple[int, float]:
        """Extract token usage and cost from response data.

        Returns:
            Tuple of (total_tokens, cost)
        """
        try:
            if provider_name == "bedrock":
                usage = data.get("usage", {})
                # Bedrock uses input_tokens and output_tokens (not inputTokens/outputTokens)
                input_tokens = usage.get("input_tokens", 0) or usage.get("inputTokens", 0)
                output_tokens = usage.get("output_tokens", 0) or usage.get("outputTokens", 0)
                total_tokens = input_tokens + output_tokens
                # Cost calculation would depend on model pricing
                cost = 0.0  # TODO: Calculate based on model and token counts
                return total_tokens, cost

            elif provider_name in ["azure", "openai"]:
                usage = data.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
                cost = 0.0  # TODO: Calculate based on model and token counts
                return total_tokens, cost

            else:
                return 0, 0.0

        except Exception as e:
            logger.error(f"Error extracting usage: {e}")
            return 0, 0.0

    def stream_with_live_rendering(
        self,
        url: str,
        payload: dict,
        mapper,
        *,
        console,
        use_thinking: bool = False,
        provider_name: str = "bedrock",
        show_model_name: bool = True,
        live_window: int = 6
    ) -> StreamResult:
        """Non-streaming version of live rendering method.

        This method exists for API compatibility with StreamingClient.
        It simply calls send_message and displays the complete result.
        """
        # Show waiting indicator
        console.print("[dim]Waiting for response…[/dim]")

        # Get complete response
        result = self.send_message(url, payload, mapper=mapper, provider_name=provider_name)

        # Display model name if available
        if result.model_name and show_model_name:
            console.rule(f"[bold cyan]{result.model_name}")

        # Display text response
        if result.text:
            console.print(result.text)

        # Display tool executions
        if result.tool_calls:
            for tool_call in result.tool_calls:
                tool_info = tool_call.get('tool_call', {})
                tool_name = tool_info.get('name', 'unknown')
                console.print(f"[yellow]⚙ Using {tool_name} tool...[/yellow]")

                if tool_call.get('result'):
                    result_text = tool_call.get('result', '')
                    if isinstance(result_text, str) and result_text:
                        console.print(f"[green]✓ {result_text}[/green]")

        # Display error if any
        if result.error:
            console.print(f"[red]Error: {result.error}[/red]")

        return result