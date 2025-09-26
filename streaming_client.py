"""StreamingClient for handling LLM SSE interactions."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Iterator
from requests.exceptions import RequestException, ReadTimeout, ConnectTimeout
import requests

from tools.executor import ToolExecutor
from rich.console import Console
from render.markdown_live import MarkdownStream
from util.input_helpers import _raw_mode, _esc_pressed

# Global abort flag for stream interruption
_ABORT = False

@dataclass
class StreamResult:
    """Result from streaming an LLM request."""
    text: str
    tokens: int
    cost: float
    tool_calls: List[dict]
    model_name: Optional[str] = None
    aborted: bool = False
    error: Optional[str] = None


@dataclass
class StreamEvent:
    """Individual event from the stream."""
    kind: str
    value: Optional[str] = None

class StreamingClient:
    """Handles streaming SSE interactions with LLM providers."""

    def __init__(self, tool_executor: Optional[ToolExecutor] = None):
        self.tool_executor = tool_executor
        self._abort = False

    def abort(self) -> None:
        """Signal the current stream to abort."""
        self._abort = True

    def iter_sse_lines(
        self,
        url: str,
        *,
        method: str = "POST",
        json: Optional[dict] = None,
        params: Optional[Dict[str, str]] = None,
        timeout: float = 60.0,
        session: Optional[requests.Session] = None,
    ) -> Iterator[str]:
        """Yield SSE data lines from an HTTP response.

        Strips the leading "data:" prefix when present and skips empty keep-alive lines.
        """
        sse_session = session or requests.Session()
        req = sse_session.get if method.upper() == "GET" else sse_session.post
        with req(url, json=json, params=params, stream=True, timeout=timeout) as r:
            r.raise_for_status()
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                yield raw[5:].lstrip() if raw.startswith("data:") else raw

    def send_message(
        self,
        url: str,
        payload: dict,
        *,
        mapper,
        provider_name: str = "bedrock"
    ) -> StreamResult:
        """Send a message and stream the response.

        Args:
            url: The endpoint URL
            payload: The request payload
            mapper: Provider-specific event mapper function
            provider_name: Name of the provider for specialized handling

        Returns:
            StreamResult with accumulated response data
        """
        # Reset abort flag
        self._abort = False

        # Accumulate response data
        text_buffer: List[str] = []
        model_name: Optional[str] = None
        tool_calls_made: List[dict] = []

        # Tool execution state
        current_tool = None
        tool_input_buffer = ""

        try:
            # Stream events and process them
            for event in self._stream_events(url, payload, mapper):
                if self._abort:
                    return StreamResult(
                        text="".join(text_buffer),
                        tokens=0,
                        cost=0.0,
                        tool_calls=tool_calls_made,
                        model_name=model_name,
                        aborted=True
                    )

                if event.kind == "model":
                    model_name = event.value or model_name

                elif event.kind == "text":
                    text_buffer.append(event.value or "")

                elif event.kind == "thinking":
                    # Thinking content - could be handled by caller
                    pass

                elif event.kind == "tool_start":
                    if self.tool_executor and event.value:
                        try:
                            current_tool = json.loads(event.value)
                            tool_input_buffer = ""
                        except json.JSONDecodeError:
                            # Invalid tool format - skip
                            pass

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
                            result = self.tool_executor.execute_tool(tool_name, tool_input)

                            # Store tool call data
                            tool_calls_made.append({
                                "tool_call": {
                                    "id": tool_id,
                                    "name": tool_name,
                                    "input": tool_input
                                },
                                "result": result['content']
                            })

                        except json.JSONDecodeError:
                            # Invalid tool input - skip
                            pass
                        finally:
                            current_tool = None

                elif event.kind == "tokens":
                    # Parse usage statistics
                    if event.value and "|" in event.value:
                        parts = event.value.split("|")
                        if len(parts) >= 4:
                            # Handle estimated tokens (with ~ prefix)
                            total_str = parts[0].lstrip("~")
                            total_tokens = int(total_str) if total_str.isdigit() else 0
                            cost = float(parts[3]) if parts[3] else 0.0
                            return StreamResult(
                                text="".join(text_buffer),
                                tokens=total_tokens,
                                cost=cost,
                                tool_calls=tool_calls_made,
                                model_name=model_name
                            )
                    # Fallback for simple token format
                    tokens = int(event.value) if event.value and event.value.isdigit() else 0
                    return StreamResult(
                        text="".join(text_buffer),
                        tokens=tokens,
                        cost=0.0,
                        tool_calls=tool_calls_made,
                        model_name=model_name
                    )

                elif event.kind == "done":
                    break

        except (ReadTimeout, ConnectTimeout) as e:
            return StreamResult(
                text="".join(text_buffer),
                tokens=0,
                cost=0.0,
                tool_calls=tool_calls_made,
                model_name=model_name,
                error=f"Request timed out: {e}"
            )
        except RequestException as e:
            return StreamResult(
                text="".join(text_buffer),
                tokens=0,
                cost=0.0,
                tool_calls=tool_calls_made,
                model_name=model_name,
                error=f"Network error: {e}"
            )
        except Exception as e:
            return StreamResult(
                text="".join(text_buffer),
                tokens=0,
                cost=0.0,
                tool_calls=tool_calls_made,
                model_name=model_name,
                error=f"Unexpected error: {e}"
            )

        # Return final result
        return StreamResult(
            text="".join(text_buffer),
            tokens=0,
            cost=0.0,
            tool_calls=tool_calls_made,
            model_name=model_name
        )

    def _stream_events(self, url: str, payload: dict, mapper) -> Iterator[StreamEvent]:
        """Stream and map SSE events."""
        try:
            for kind, value in mapper(self.iter_sse_lines(url, json=payload)):
                yield StreamEvent(kind=kind, value=value)
        except Exception:
            # Let the caller handle the exception
            raise

    def stream_with_live_rendering(
        self,
        url: str,
        payload: dict,
        mapper,
        *,
        console: Console,
        use_thinking: bool = False,
        provider_name: str = "bedrock",
        show_model_name: bool = True,
        live_window: int = 6
    ) -> StreamResult:
        """Stream response with live Markdown rendering and tool execution."""
        # Create markdown stream for live rendering (pass console for width-aware wrapping)
        ms = MarkdownStream(live_window=live_window)

        # Set up abort handling
        global _ABORT
        _ABORT = False

        # State tracking
        text_buffer = []
        tool_calls_made = []
        model_name = None
        current_tool = None
        tool_input_buffer = ""

        try:
            with _raw_mode(sys.stdin):
                # Show waiting indicator until first content arrives
                if use_thinking and provider_name == "azure":
                    ms.start_waiting("Thinking…")
                else:
                    ms.start_waiting("Waiting for response…")

                # Stream events and render them live while collecting data
                for event in self._stream_events(url, payload, mapper):
                    # Check for abort (ESC key)
                    if _ABORT or _esc_pressed(0.0):
                        _ABORT = True
                        break

                    if event.kind == "model":
                        ms.stop_waiting()
                        model_name = event.value or model_name
                        if model_name and show_model_name:
                            console.rule(f"[bold cyan]{model_name}")

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
                                # Ensure any pending text is rendered before showing tool message
                                ms.update("".join(text_buffer), final=False)
                                # Show tool message immediately
                                console.print(f"[yellow]⚙ Using {current_tool.get('name')} tool...[/yellow]")
                            except json.JSONDecodeError:
                                console.print("[red]Error: Invalid tool start format[/red]")

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

                                # Display tool result
                                if "error" in result_data:
                                    console.print(f"[red]Tool error: {result_data['error']}[/red]")
                                else:
                                    console.print(f"[green]✓ {result_data['content']}[/green]")

                                tool_result_content = result_data['content']
                                # Store tool call data
                                tool_calls_made.append({
                                    "tool_call": {
                                        "id": tool_id,
                                        "name": tool_name,
                                        "input": tool_input
                                    },
                                    "result": tool_result_content
                                })

                            except json.JSONDecodeError:
                                console.print("[red]Error: Invalid tool input JSON[/red]")
                            finally:
                                current_tool = None
                                tool_input_buffer = ""

                    elif event.kind == "tokens":
                        # Parse usage statistics
                        if event.value and "|" in event.value:
                            parts = event.value.split("|")
                            if len(parts) >= 4:
                                # Handle estimated tokens (with ~ prefix)
                                total_str = parts[0].lstrip("~")
                                total_tokens = int(total_str) if total_str.isdigit() else 0
                                cost = float(parts[3]) if parts[3] else 0.0
                                result = StreamResult(
                                    text="".join(text_buffer),
                                    tokens=total_tokens,
                                    cost=cost,
                                    tool_calls=tool_calls_made,
                                    model_name=model_name,
                                    aborted=_ABORT
                                )
                                ms.update("".join(text_buffer), final=True)
                                return result
                        # Fallback for simple token format
                        tokens = int(event.value) if event.value and event.value.isdigit() else 0
                        result = StreamResult(
                            text="".join(text_buffer),
                            tokens=tokens,
                            cost=0.0,
                            tool_calls=tool_calls_made,
                            model_name=model_name,
                            aborted=_ABORT
                        )
                        ms.update("".join(text_buffer), final=True)
                        return result

                    elif event.kind == "done":
                        break

        except Exception as e:
            ms.stop_waiting()
            console.print(f"[red]Error[/red]: {e}")
            return StreamResult(
                text="".join(text_buffer),
                tokens=0,
                cost=0.0,
                tool_calls=tool_calls_made,
                model_name=model_name,
                aborted=_ABORT,
                error=str(e)
            )
        finally:
            # Finalize markdown rendering
            ms.update("".join(text_buffer), final=True)
            if _ABORT:
                console.print("[dim]Aborted[/dim]")

        # Return final result
        result = StreamResult(
            text="".join(text_buffer),
            tokens=0,
            cost=0.0,
            tool_calls=tool_calls_made,
            model_name=model_name,
            aborted=_ABORT
        )

        return result
