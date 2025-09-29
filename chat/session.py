"""Chat session orchestration and API interactions."""

from typing import List
from rich.console import Console

from streaming_client import StreamingClient, StreamResult

console = Console(soft_wrap=True)


class ChatSession:
    """Orchestrates API interactions and tool execution flows."""

    def __init__(self, url: str, provider, max_tokens: int, timeout: float,
                 tool_executor, provider_name: str = "bedrock"):
        self.url = url
        self.provider = provider
        self.provider_name = provider_name
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.tool_executor = tool_executor
        self.streaming_client = StreamingClient(tool_executor=tool_executor)

    def send_message(self, history: List[dict], use_thinking: bool, tools_enabled: bool,
                    available_tools) -> StreamResult:
        """Send a message and handle the complete request/response cycle including tools."""
        # Build request payload with conditional tool support and context injection
        tools_param = available_tools if tools_enabled else None

        messages_for_llm = list(history)
        extra_kwargs = {}

        payload = self.provider.build_payload(
            messages_for_llm,
            model=None,
            max_tokens=self.max_tokens,
            thinking=use_thinking,
            tools=tools_param,
            **extra_kwargs,
        )

        # Stream initial response and capture any tool calls
        result = self.streaming_client.send_message(
            self.url,
            payload,
            mapper=self.provider.map_events,
            provider_name=self.provider_name,
        )

        return result

    def handle_tool_followup(self, history: List[dict], use_thinking: bool, tools_enabled: bool,
                           available_tools) -> StreamResult:
        """Handle follow-up request after tool execution."""

        # Follow-up request includes tool results in context
        tools_param = available_tools if tools_enabled else None
        followup_payload = self.provider.build_payload(history, model=None, max_tokens=self.max_tokens,
                                                      thinking=use_thinking, tools=tools_param)

        result = self.streaming_client.send_message(
            self.url,
            followup_payload,
            mapper=self.provider.map_events,
            provider_name=self.provider_name,
        )

        return result
