"""
LLM client for handling language model interactions.

This module provides a clean interface for LLM communication,
tool calling, and response processing.
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from rich.console import Console
from rich.markdown import CodeBlock, Heading, Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text


class _CodeBlockTight(CodeBlock):
    def __rich_console__(self, console, options):
        code = str(self.text).rstrip()
        syntax = Syntax(
            code, self.lexer_name, theme=self.theme, word_wrap=True, padding=(1, 0)
        )
        yield syntax


class _HeadingLeft(Heading):
    def __rich_console__(self, console, options):
        text = self.text
        text.justify = "left"
        if self.tag == "h1":
            yield Panel(text, box=box.HEAVY, style="markdown.h1.border")
        else:
            if self.tag == "h2":
                yield Text("")
            yield text


class MarkdownStyled(Markdown):
    elements = {
        **Markdown.elements,
        "fence": _CodeBlockTight,
        "code_block": _CodeBlockTight,
        "heading_open": _HeadingLeft,
    }


logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Response from LLM including text and tool calls."""

    text: str
    tools_used: List[str]
    tool_results: Dict[str, str]
    tool_calls: List[dict]
    tokens: int = 0
    cost: float = 0.0
    error: Optional[str] = None


class LLMClient:
    """Client for LLM interactions with tool calling support."""

    def __init__(self, session=None, console: Optional[Console] = None):
        """
        Initialize the LLM client.

        Args:
            session: ChatSession for LLM communication
            console: Rich console for output
        """
        self.session = session
        self.console = console or Console()

    def call_llm(
        self, messages: List[Dict[str, Any]], tool_schemas: List[Dict[str, Any]]
    ) -> LLMResponse:
        """
        Call the LLM with conversation messages and tool schemas.

        Args:
            messages: Conversation messages
            tool_schemas: Available tool schemas for function calling

        Returns:
            LLMResponse with text and tool execution results
        """
        if not self.session:
            logger.warning("No session available, using mock response")
            return self._get_mock_response(messages[-1]["content"])

        try:
            return self._call_real_llm(messages, tool_schemas)
        except Exception as e:
            logger.error(f"Error calling LLM: {e}")
            return self._get_error_response(str(e))

    def _call_real_llm(
        self, messages: List[Dict[str, Any]], tool_schemas: List[Dict[str, Any]]
    ) -> LLMResponse:
        """Call the real LLM through the session."""
        if (
            not hasattr(self.session, "streaming_client")
            or not self.session.streaming_client
        ):
            logger.warning("No streaming client available, using mock response")
            return self._get_mock_response(messages[-1]["content"])

        # Separate system prompt from messages
        system_prompt = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                cleaned_msg = copy.deepcopy(msg)
                self._strip_prompt_caching_from_message(cleaned_msg)
                user_messages.append(cleaned_msg)

        if self._should_apply_prompt_caching():
            self._apply_prompt_caching(user_messages)

        # Build payload using the provider
        payload = self.session.provider.build_payload(
            user_messages,
            model=None,
            max_tokens=self.session.max_tokens,
            thinking=False,
            tools=tool_schemas,
            context_content=None,
            rag_enabled=False,
            system_prompt=system_prompt,
        )

        # Send message and get results
        result = self.session.streaming_client.send_message(
            self.session.url,
            payload,
            mapper=self.session.provider.map_events,
            provider_name=getattr(self.session, "provider_name", "bedrock"),
        )

        # Display the response with Rich markdown formatting
        if result.text:
            self.console.print(MarkdownStyled(result.text.strip()))

        # Track usage if available
        if hasattr(self.session, "usage_tracker") and self.session.usage_tracker:
            if result.tokens > 0 or result.cost > 0:
                self.session.usage_tracker.update(result.tokens, result.cost)

        # Process tool calls and results
        # Note: Tool execution messages are now displayed by ToolExecutionService
        # during execution, so we just collect the results here
        tools_used = []
        tool_results = {}
        tool_calls = []

        if result.tool_calls:
            for tool_call in result.tool_calls:
                # tool_call is a ToolCall object, not a dict
                tool_name = tool_call.name
                tools_used.append(tool_name)

                # Store full result for tool_results (for LLM context)
                if tool_call.result:
                    tool_results[tool_name] = tool_call.result

                tool_calls.append(tool_call)

        return LLMResponse(
            text=(result.text or "").strip(),
            tools_used=tools_used,
            tool_results=tool_results,
            tool_calls=tool_calls,
            tokens=getattr(result, "tokens", 0),
            cost=getattr(result, "cost", 0.0),
            error=getattr(result, "error", None),
        )

    def _should_apply_prompt_caching(self) -> bool:
        """Return True when provider supports Anthropic prompt caching."""
        if not self.session:
            return False

        provider = getattr(self.session, "provider", None)
        if provider is not None:
            supports_prompt_caching = getattr(provider, "supports_prompt_caching", None)
            if supports_prompt_caching is not None:
                return bool(supports_prompt_caching)

        return False

    def _apply_prompt_caching(self, messages: List[Dict[str, Any]]) -> None:
        """Mark older conversation context as cacheable for Anthropic."""
        if len(messages) <= 4:
            return

        cache_index = len(messages) - 4
        if cache_index < 0 or cache_index >= len(messages):
            return

        target_message = messages[cache_index]
        cache_control = dict(target_message.get("cache_control") or {})
        cache_control["type"] = "ephemeral"
        target_message["cache_control"] = cache_control

    def _strip_prompt_caching_metadata(self, messages: List[Dict[str, Any]]) -> None:
        for message in messages:
            self._strip_prompt_caching_from_message(message)

    def _strip_prompt_caching_from_message(self, message: Dict[str, Any]) -> None:
        if not isinstance(message, dict):
            return
        message.pop("cache_control", None)
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    block.pop("cache_control", None)

    def _get_mock_response(self, user_query: str) -> LLMResponse:
        """Generate a mock response for testing/fallback."""
        import json
        import re

        query_lower = user_query.lower()

        # Mock response based on query patterns
        if "validation" in query_lower or "validates" in query_lower:
            if "product" in query_lower:
                text = """
Thought: I need to analyze validations for the Product model. Let me examine the Product model file to find validation rules.

Action: model_analyzer
Input: {"model_name": "Product", "focus": "validations"}
"""
            else:
                text = """
Thought: I need to find validation-related code. Let me search for validation patterns in the codebase.

Action: ripgrep
Input: {"pattern": "validates", "file_types": ["rb"]}
"""

        elif (
            "callback" in query_lower
            or "before" in query_lower
            or "after" in query_lower
        ):
            text = """
Thought: This query is about Rails callbacks. I should examine model files for callback definitions.

Action: ripgrep
Input: {"pattern": "before_|after_|around_", "file_types": ["rb"]}
"""

        elif "controller" in query_lower:
            text = """
Thought: This is a controller-related query. Let me analyze the relevant controller.

Action: controller_analyzer
Input: {"controller_name": "Application", "action": "all"}
"""

        elif (
            "select" in query_lower and "from" in query_lower
        ) or "sql" in query_lower:
            # Extract the actual SQL query from the user message
            sql_match = re.search(
                r"SELECT\s+.*?FROM\s+.*?(?:ORDER\s+BY\s+.*?)?(?:LIMIT\s+\d+)?",
                user_query,
                re.IGNORECASE | re.DOTALL,
            )
            actual_sql = sql_match.group(0) if sql_match else user_query

            text = f"""
Thought: This is a SQL query tracing request. I should use the enhanced SQL search tool to find the exact Rails source code that generates this query with confidence scoring.

Action: enhanced_sql_rails_search
Input: {json.dumps({"sql": actual_sql})}
"""

        else:
            text = """
Thought: I need to search for SQL-related code in this Rails project to find where this query might be generated.

Action: ripgrep
Input: {"pattern": "SELECT|WHERE|FROM", "file_types": ["rb", "erb"]}
"""

        return LLMResponse(
            text=text.strip(), tools_used=[], tool_results={}, tool_calls=[]
        )

    def _get_error_response(self, error_message: str) -> LLMResponse:
        """Generate an error response."""
        return LLMResponse(
            text=f"Error in LLM communication: {error_message}",
            tools_used=[],
            tool_results={},
            tool_calls=[],
            error=error_message,
        )

    def format_tool_messages(self, tool_calls_made: List[dict]) -> List[dict]:
        """
        Format tool calls and results into Anthropic tool_use/tool_result messages.

        Args:
            tool_calls_made: List of ToolCall objects

        Returns:
            List of formatted messages for conversation context
        """
        if not tool_calls_made:
            return []

        # Create tool_use blocks
        tool_use_blocks = []
        for tool_call in tool_calls_made:
            # tool_call is a ToolCall object
            tool_use_blocks.append(
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": tool_call.input,
                }
            )

        # Create tool_result blocks
        tool_result_blocks = []
        for tool_call in tool_calls_made:
            # tool_call is a ToolCall object
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": tool_call.result,
                }
            )

        return [
            {"role": "assistant", "content": tool_use_blocks},
            {"role": "user", "content": tool_result_blocks},
        ]

    def has_session(self) -> bool:
        """Check if a valid session is available."""
        return self.session is not None

    def get_session_info(self) -> Dict[str, Any]:
        """Get information about the current session."""
        if not self.session:
            return {"status": "no_session"}

        return {
            "status": "active",
            "provider_name": getattr(self.session, "provider_name", "unknown"),
            "has_streaming_client": hasattr(self.session, "streaming_client")
            and self.session.streaming_client is not None,
            "max_tokens": getattr(self.session, "max_tokens", None),
            "timeout": getattr(self.session, "timeout", None),
        }
