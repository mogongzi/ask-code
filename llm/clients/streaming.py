"""
Streaming (SSE) LLM client.

Handles Server-Sent Events (SSE) streaming with live rendering.
Refactored to use new infrastructure while preserving streaming capabilities.
"""

from __future__ import annotations

import json
import sys
import logging
from typing import Optional, Iterator, Dict
from dataclasses import dataclass
import requests
from requests.exceptions import RequestException, ReadTimeout, ConnectTimeout

from llm.types import LLMResponse, Provider
from llm.clients.base import BaseLLMClient
from tools.executor import ToolExecutor
from rich.console import Console
from render.markdown_live import MarkdownStream
from util.input_helpers import _raw_mode, _esc_pressed

logger = logging.getLogger(__name__)


@dataclass
class StreamEvent:
    """Individual event from the SSE stream."""
    kind: str
    value: Optional[str] = None


class StreamingClient(BaseLLMClient):
    """Streaming (SSE) LLM client.

    Handles Server-Sent Events streaming for real-time LLM responses.
    Shows live markdown rendering as content arrives.

    This is the refactored version using new infrastructure:
    - Inherits from BaseLLMClient (Template Method pattern)
    - Uses ParserRegistry for response parsing
    - Uses ToolExecutionService for tool execution
    - Uses ErrorHandler for error handling

    Unlike BlockingClient, this client:
    - Streams events in real-time (SSE)
    - Renders content as it arrives
    - Supports abort/interrupt (ESC key)
    - Has two modes: basic send_message() and full stream_with_live_rendering()
    """

    def __init__(
        self,
        tool_executor: Optional[ToolExecutor] = None,
        console: Optional[Console] = None,
        provider: Provider = Provider.BEDROCK,
        timeout: float = 60.0
    ):
        """Initialize streaming client.

        Args:
            tool_executor: Optional tool executor for function calling
            console: Rich console for output
            provider: Provider type (determines parser)
            timeout: Default request timeout in seconds
        """
        super().__init__(tool_executor, console, provider)
        self.timeout = timeout

    def _make_request(
        self,
        url: str,
        payload: dict,
        timeout: Optional[float] = None,
        **kwargs
    ) -> dict:
        """Make streaming SSE request and accumulate complete response.

        This is used by the base class send_message() method for simple
        streaming without live rendering. For full live rendering, use
        stream_with_live_rendering() directly.

        Args:
            url: Endpoint URL (should be streaming endpoint)
            payload: Request payload
            timeout: Request timeout (uses default if not specified)
            **kwargs: Additional arguments (mapper, provider_name)

        Returns:
            Complete response data as dict (accumulated from stream)

        Raises:
            ReadTimeout, ConnectTimeout, RequestException: On errors
        """
        mapper = kwargs.get("mapper")
        if not mapper:
            raise ValueError("Streaming requires a mapper function")

        # Accumulate complete response
        text_parts = []
        tool_calls = []
        model_name = None
        usage_info = None

        # Tool execution state
        current_tool = None
        tool_input_buffer = ""

        def _safe_int(value: Optional[str]) -> int:
            try:
                if value is None:
                    return 0
                return int(float(value))
            except (ValueError, TypeError):
                return 0

        def _safe_float(value: Optional[str]) -> float:
            try:
                if value in (None, ""):
                    return 0.0
                return float(value)
            except (ValueError, TypeError):
                return 0.0

        try:
            # Stream events and accumulate them
            for event in self._stream_events(url, payload, mapper, timeout):
                if self._abort:
                    break

                if event.kind == "model":
                    model_name = event.value

                elif event.kind == "text":
                    text_parts.append(event.value or "")

                elif event.kind == "tool_start":
                    if event.value:
                        try:
                            current_tool = json.loads(event.value)
                            tool_input_buffer = ""
                        except json.JSONDecodeError:
                            logger.warning("Invalid tool start format")

                elif event.kind == "tool_input_delta":
                    if event.value:
                        tool_input_buffer += event.value

                elif event.kind == "tool_ready":
                    if current_tool:
                        try:
                            tool_input = json.loads(tool_input_buffer) if tool_input_buffer else {}
                            tool_calls.append({
                                "id": current_tool.get("id"),
                                "name": current_tool.get("name"),
                                "input": tool_input
                            })
                        except json.JSONDecodeError:
                            logger.warning("Invalid tool input JSON")
                        finally:
                            current_tool = None

                elif event.kind == "tokens":
                    # Parse usage statistics
                    if event.value and "|" in event.value:
                        parts = event.value.split("|")
                        if len(parts) >= 4:
                            total_str = parts[0].lstrip("~")
                            input_str = parts[1].lstrip("~")
                            output_str = parts[2].lstrip("~")
                            cost_str = parts[3]

                            usage_info = {
                                "total_tokens": _safe_int(total_str),
                                "input_tokens": _safe_int(input_str),
                                "output_tokens": _safe_int(output_str),
                                "cost": _safe_float(cost_str),
                            }
                    else:
                        usage_info = {
                            "total_tokens": _safe_int(event.value),
                            "input_tokens": 0,
                            "output_tokens": 0,
                            "cost": 0.0,
                        }

                elif event.kind == "done":
                    break

            # Build complete response in format expected by parsers
            # This is a synthetic response structure that mimics Bedrock format
            usage_block = {
                "inputTokens": 0,
                "outputTokens": 0,
                "totalTokens": 0,
                "cost": 0.0,
            }

            if usage_info:
                usage_block.update(
                    {
                        "inputTokens": usage_info.get("input_tokens", 0),
                        "outputTokens": usage_info.get("output_tokens", 0),
                        "totalTokens": usage_info.get("total_tokens", 0),
                        "cost": usage_info.get("cost", 0.0),
                        "input_tokens": usage_info.get("input_tokens", 0),
                        "output_tokens": usage_info.get("output_tokens", 0),
                        "total_tokens": usage_info.get("total_tokens", 0),
                    }
                )

            complete_response = {
                "content": [{"type": "text", "text": "".join(text_parts)}],
                "stopReason": "end_turn" if not self._abort else "aborted",
                "usage": usage_block,
            }

            # Add model name if available
            if model_name:
                complete_response["model"] = model_name

            # Add tool calls if any
            if tool_calls:
                complete_response["content"].insert(0, {
                    "type": "tool_use",
                    "toolUse": tool_calls
                })

            return complete_response

        except (ReadTimeout, ConnectTimeout) as e:
            logger.error(f"Streaming timeout: {e}")
            raise
        except RequestException as e:
            logger.error(f"Streaming network error: {e}")
            raise

    def iter_sse_lines(
        self,
        url: str,
        *,
        method: str = "POST",
        json_data: Optional[dict] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        session: Optional[requests.Session] = None,
    ) -> Iterator[str]:
        """Yield SSE data lines from an HTTP response.

        Strips the leading "data:" prefix when present and skips empty keep-alive lines.

        Args:
            url: Endpoint URL
            method: HTTP method (GET or POST)
            json_data: JSON payload for POST
            params: URL parameters
            timeout: Request timeout
            session: Optional requests session

        Yields:
            SSE data lines (without "data:" prefix)
        """
        sse_session = session or requests.Session()
        req = sse_session.get if method.upper() == "GET" else sse_session.post

        with req(url, json=json_data, params=params, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                yield raw[5:].lstrip() if raw.startswith("data:") else raw

    def _stream_events(
        self,
        url: str,
        payload: dict,
        mapper,
        timeout: Optional[float] = None
    ) -> Iterator[StreamEvent]:
        """Stream and map SSE events.

        Args:
            url: Endpoint URL
            payload: Request payload
            mapper: Provider-specific event mapper function
            timeout: Request timeout

        Yields:
            StreamEvent objects
        """
        timeout_val = timeout or self.timeout
        try:
            for kind, value in mapper(self.iter_sse_lines(url, json_data=payload, timeout=timeout_val)):
                yield StreamEvent(kind=kind, value=value)
        except Exception:
            raise

    def stream_with_live_rendering(
        self,
        url: str,
        payload: dict,
        mapper,
        *,
        console: Optional[Console] = None,
        use_thinking: bool = False,
        provider_name: str = "bedrock",
        show_model_name: bool = True,
        live_window: int = 6
    ) -> LLMResponse:
        """Stream response with live Markdown rendering and tool execution.

        This is the full-featured streaming mode with:
        - Live markdown rendering as content arrives
        - Real-time tool execution display
        - Abort support (ESC key)
        - Thinking content rendering (for Azure)

        Args:
            url: Endpoint URL
            payload: Request payload
            mapper: Provider-specific event mapper
            console: Console for output (uses instance console if not provided)
            use_thinking: Whether to show thinking content
            provider_name: Provider name string
            show_model_name: Whether to display model name
            live_window: Number of lines for live rendering window

        Returns:
            LLMResponse with complete results
        """
        # Use provided console or instance console
        output_console = console or self.console

        # Create markdown stream for live rendering
        ms = MarkdownStream(live_window=live_window)

        # Reset abort flag
        self._abort = False

        # State tracking
        text_buffer = []
        tool_calls_made = []
        model_name = None
        usage_data = None
        current_tool = None
        tool_input_buffer = ""

        try:
            with _raw_mode(sys.stdin):
                # Show waiting indicator until first content arrives
                if use_thinking and provider_name == "azure":
                    ms.start_waiting("Thinking…")
                else:
                    ms.start_waiting("Waiting for response…")

                # Stream events and render them live
                for event in self._stream_events(url, payload, mapper):
                    # Check for abort (ESC key)
                    if self._abort or _esc_pressed(0.0):
                        self._abort = True
                        break

                    if event.kind == "model":
                        ms.stop_waiting()
                        model_name = event.value or model_name
                        if model_name and show_model_name:
                            output_console.rule(f"[bold cyan]{model_name}")

                    elif event.kind == "thinking":
                        ms.stop_waiting()
                        ms.add_thinking(event.value or "")

                    elif event.kind == "text":
                        ms.stop_waiting()
                        text_buffer.append(event.value or "")
                        ms.add_response(event.value or "")

                    elif event.kind == "tool_start":
                        ms.stop_waiting()
                        if self.tool_executor and event.value:
                            try:
                                current_tool = json.loads(event.value)
                                tool_input_buffer = ""
                                # Ensure any pending text is rendered
                                ms.update("".join(text_buffer), final=False)
                                # Show tool message
                                output_console.print(f"[yellow]⚙ Using {current_tool.get('name')} tool...[/yellow]")
                            except json.JSONDecodeError:
                                output_console.print("[red]Error: Invalid tool start format[/red]")

                    elif event.kind == "tool_input_delta":
                        if event.value:
                            tool_input_buffer += event.value

                    elif event.kind == "tool_ready":
                        if self.tool_executor and current_tool:
                            try:
                                tool_input = json.loads(tool_input_buffer) if tool_input_buffer else {}
                                tool_name = current_tool.get("name")
                                tool_id = current_tool.get("id")

                                # Execute the tool
                                result_data = self.tool_executor.execute_tool(tool_name, tool_input)

                                # Display tool result (use compact version for UI)
                                display_text = result_data.get('display', result_data.get('content', ''))
                                if "error" in result_data:
                                    output_console.print(f"[red]Tool error: {result_data['error']}[/red]")
                                else:
                                    output_console.print(f"[green]✓ {display_text}[/green]")

                                # Store tool call data (full version for conversation)
                                tool_calls_made.append({
                                    "tool_call": {
                                        "id": tool_id,
                                        "name": tool_name,
                                        "input": tool_input
                                    },
                                    "result": result_data.get('content', ''),
                                    "display_result": display_text
                                })

                            except json.JSONDecodeError:
                                output_console.print("[red]Error: Invalid tool input JSON[/red]")
                            finally:
                                current_tool = None
                                tool_input_buffer = ""

                    elif event.kind == "tokens":
                        # Parse usage statistics
                        if event.value and "|" in event.value:
                            parts = event.value.split("|")
                            if len(parts) >= 4:
                                total_str = parts[0].lstrip("~")
                                usage_data = {
                                    "total_tokens": int(total_str) if total_str.isdigit() else 0,
                                    "cost": float(parts[3]) if parts[3] else 0.0
                                }
                        else:
                            usage_data = {
                                "total_tokens": int(event.value) if event.value and event.value.isdigit() else 0,
                                "cost": 0.0
                            }

                    elif event.kind == "done":
                        break

        except Exception as e:
            ms.stop_waiting()
            output_console.print(f"[red]Error[/red]: {e}")
            # Continue to build response with error

        finally:
            # Finalize markdown rendering
            ms.update("".join(text_buffer), final=True)
            if self._abort:
                output_console.print("[dim]Aborted[/dim]")

        # Convert tool calls to ToolCall objects
        from llm.types import ToolCall
        tool_call_objects = [
            ToolCall(
                id=tc["tool_call"]["id"],
                name=tc["tool_call"]["name"],
                input=tc["tool_call"]["input"],
                result=tc.get("result", ""),
                display_result=tc.get("display_result", "")
            )
            for tc in tool_calls_made
        ]

        # Build final LLMResponse
        return LLMResponse(
            text="".join(text_buffer),
            tokens=usage_data.get("total_tokens", 0) if usage_data else 0,
            cost=usage_data.get("cost", 0.0) if usage_data else 0.0,
            tool_calls=tool_call_objects,
            model_name=model_name,
            aborted=self._abort
        )

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"StreamingClient("
            f"provider={self.provider.value}, "
            f"timeout={self.timeout}s, "
            f"has_tools={self._has_tools()})"
        )
