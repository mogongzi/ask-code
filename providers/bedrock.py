from __future__ import annotations

import copy
import json
from typing import Dict, Iterator, Optional, Tuple, List, Union


Event = Tuple[str, Optional[str]]  # ("model"|"text"|"thinking"|"tool_start"|"tool_input_delta"|"tool_ready"|"done"|"tokens", value)

# Bedrock Anthropic now supports prompt caching via cache_control metadata.
supports_prompt_caching = True
# Message-level cache_control is now supported for last-two-user-messages caching.
supports_message_cache_control = True

# Approximate maximum context window for common Bedrock Anthropic models.
# Claude 4 Sonnet supports ~200k tokens context.
# Exposed so the CLI can size its usage indicator appropriately.
context_length: int = 200_000


def _format_system_prompt(system_prompt: Optional[Union[str, List[dict]]]) -> Optional[List[dict]]:
    """Format system prompt into Anthropic block structure with cache metadata.

    Strategy: Put cache breakpoint on the LAST system block only (not all blocks).
    This ensures system prompt meets minimum token requirements (usually 1024+)
    while using only 1 breakpoint for the entire static prefix.

    If tools are also provided, the system breakpoint takes precedence;
    tools don't need their own breakpoint (they're cached with system).
    """
    if system_prompt is None:
        return None

    # When the prompt is already block-structured, strip existing cache_control
    # and add only to the last block.
    if isinstance(system_prompt, list):
        formatted_blocks: List[dict] = []
        for block in system_prompt:
            if not isinstance(block, dict):
                continue
            prepared_block = copy.deepcopy(block)
            # Remove any existing cache_control - we'll add only to the last block
            prepared_block.pop("cache_control", None)
            formatted_blocks.append(prepared_block)

        # Add cache_control only to the LAST block
        if formatted_blocks:
            formatted_blocks[-1]["cache_control"] = {"type": "ephemeral"}

        return formatted_blocks or None

    if not isinstance(system_prompt, str):
        return None

    marker = "# Tool Usage (ReAct Pattern)"
    instructions_text = system_prompt
    tool_text = ""

    if marker in system_prompt:
        instructions_text, remainder = system_prompt.split(marker, 1)
        tool_text = f"{marker}{remainder}"

    blocks: List[dict] = []

    instructions_text = instructions_text.strip()
    if instructions_text:
        blocks.append({
            "type": "text",
            "text": instructions_text,
            # NO cache_control here - only on the last block
        })

    tool_text = tool_text.strip()
    if tool_text:
        blocks.append({
            "type": "text",
            "text": tool_text,
            # NO cache_control here - only on the last block
        })

    if not blocks:
        blocks.append({
            "type": "text",
            "text": system_prompt.strip(),
        })

    # Add cache_control only to the LAST block
    if blocks:
        blocks[-1]["cache_control"] = {"type": "ephemeral"}

    return blocks


def build_payload(
    messages: List[dict], *, model: Optional[str] = None, max_tokens: int = 4096, temperature: Optional[float] = None, thinking: bool = False, thinking_tokens: int = 1024, tools: Optional[List[dict]] = None, system_prompt: Optional[Union[str, List[dict]]] = None, stop_sequences: Optional[List[str]] = None, **_: dict
) -> dict:
    """Construct Bedrock/Anthropic-style chat payload.

    Notes:
    - Do not include a 'model' key by default; many Bedrock endpoints select model via path/config.
    - Keep structure aligned with existing behavior for backward compatibility.
    - If context_content is provided, it will be prepended to the first user message.
    """
    processed_messages = messages

    # Build payload with system prompt first (for better readability)
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
    }

    # Anthropic-style API supports top-level 'system' for instructions
    # Track whether system has a cache breakpoint for tool fallback logic
    system_has_cache = False
    if system_prompt:
        formatted_system = _format_system_prompt(system_prompt)
        if formatted_system:
            payload["system"] = formatted_system
            system_has_cache = True  # _format_system_prompt adds cache to last block

    # Cache strategy for static prefix:
    # 1. If system prompt exists: it has the cache breakpoint (from _format_system_prompt)
    # 2. If no system but tools exist: add cache to last tool (fallback)
    # 3. Never cache both system AND tools (wastes breakpoints)
    if tools:
        if not system_has_cache:
            # No system prompt - use last tool as static cache point
            tools[-1]["cache_control"] = {"type": "ephemeral"}
        # else: system has the breakpoint, tools don't need one
        payload["tools"] = tools

    # Messages should come after system prompt and tool definitions
    payload["messages"] = processed_messages

    if thinking:
        payload["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_tokens
        }

    # Optional stop sequences (Anthropic-compatible)
    if stop_sequences:
        payload["stop_sequences"] = stop_sequences

    return payload


def _inject_context_into_messages(messages: List[dict], context_content: str) -> List[dict]:
    """Inject context content into the first user message.

    Args:
        messages: Original conversation messages
        context_content: Formatted context content to inject

    Returns:
        New message list with context injected
    """
    if not messages or not context_content.strip():
        return messages

    # Create a copy of messages to avoid modifying the original
    processed_messages = []

    # Find the first user message and inject context
    context_injected = False
    for message in messages:
        if message.get("role") == "user" and not context_injected:
            # Inject context before the first user message content
            original_content = message.get("content", "")
            new_content = f"{context_content}\n\n{original_content}" if original_content else context_content

            processed_messages.append({
                **message,
                "content": new_content
            })
            context_injected = True
        else:
            # Copy message as-is
            processed_messages.append(message)

    return processed_messages


def map_events(lines: Iterator[str]) -> Iterator[Event]:
    """Map Bedrock/Anthropic JSON SSE frames to a simple event interface.

    Emits:
    - ("model", model_name) on message_start
    - ("thinking", text_chunk) on content_block_delta.thinking_delta
    - ("text", text_chunk) on content_block_delta.text_delta
    - ("tool_start", tool_info_json) on content_block_start with tool_use
    - ("tool_input_delta", partial_json) on content_block_delta.input_json_delta
    - ("tool_ready", None) on content_block_stop (tool input complete)
    - ("tokens", token_count_str) on message_stop with usage info
    - ("done", None) on message_stop or [DONE]
    """
    for data in lines:
        if data == "[DONE]":
            yield ("done", None)
            break
        try:
            evt: Dict = json.loads(data)
        except json.JSONDecodeError:
            continue
        e_type = evt.get("type")
        if e_type == "message_start" and isinstance(evt.get("message"), dict):
            model = evt["message"].get("model")
            if model:
                yield ("model", model)
        elif e_type == "content_block_start":
            # Handle tool_use block start - store for later completion
            content_block = evt.get("content_block", {})
            if content_block.get("type") == "tool_use":
                # Store tool info, input will be streamed separately
                yield ("tool_start", json.dumps({
                    "id": content_block.get("id"),
                    "name": content_block.get("name")
                }))
        elif e_type == "content_block_delta":
            delta = evt.get("delta", {})
            if delta.get("type") == "thinking_delta":
                thinking = delta.get("thinking", "")
                if thinking:
                    yield ("thinking", thinking)
            elif delta.get("type") == "text_delta":
                text = delta.get("text", "")
                if text:
                    yield ("text", text)
            elif delta.get("type") == "input_json_delta":
                # Handle streaming tool input JSON
                partial_json = delta.get("partial_json", "")
                if partial_json:
                    yield ("tool_input_delta", partial_json)
        elif e_type == "content_block_stop":
            # Tool input streaming is complete, signal to execute
            yield ("tool_ready", None)
        elif e_type == "message_stop":
            # Extract usage (message_stop can nest usage under "message")
            usage_dict = evt.get("usage")
            if not isinstance(usage_dict, dict):
                usage_dict = {}
            message = evt.get("message")
            message_usage = {}
            if isinstance(message, dict) and isinstance(message.get("usage"), dict):
                message_usage = message.get("usage", {}) or {}

            def _has_cache_fields(candidate: dict) -> bool:
                return any(
                    key in candidate
                    for key in (
                        "cache_creation",
                        "cache_creation_input_tokens",
                        "cacheCreationInputTokens",
                        "cache_read_input_tokens",
                        "cacheReadInputTokens",
                    )
                )

            if message_usage and (not usage_dict or _has_cache_fields(message_usage)):
                usage_dict = message_usage

            # Token counts
            input_tokens = (
                usage_dict.get("input_tokens") or
                usage_dict.get("inputTokens") or 0
            )
            output_tokens = (
                usage_dict.get("output_tokens") or
                usage_dict.get("outputTokens") or 0
            )

            # Cache metrics - from usage dict
            cache_creation_obj = usage_dict.get("cache_creation", {})
            ephemeral_5m = (cache_creation_obj.get("ephemeral_5m_input_tokens", 0) or 0)
            ephemeral_1h = (cache_creation_obj.get("ephemeral_1h_input_tokens", 0) or 0)
            nested_sum = ephemeral_5m + ephemeral_1h

            # Use nested sum if non-zero, otherwise fall back to flat field
            if nested_sum > 0:
                cache_creation = nested_sum
            else:
                cache_creation = (
                    usage_dict.get("cache_creation_input_tokens") or
                    usage_dict.get("cacheCreationInputTokens") or 0
                )

            cache_read = (
                usage_dict.get("cache_read_input_tokens") or
                usage_dict.get("cacheReadInputTokens") or 0
            )

            # Total tokens for context tracking includes cache read tokens
            total_tokens = input_tokens + output_tokens + cache_read

            if input_tokens > 0 or output_tokens > 0 or cache_read > 0 or cache_creation > 0:
                # Calculate cost with cache-specific pricing
                # Claude 4.5 Sonnet pricing on Bedrock
                INPUT_RATE = 0.00223      # $2.23 per 1M tokens
                OUTPUT_RATE = 0.01087     # $10.87 per 1M tokens
                CACHE_WRITE_RATE = 0.00254  # 25% more than input
                CACHE_READ_RATE = 0.00020   # 90% less than input

                input_cost = (input_tokens / 1000) * INPUT_RATE
                output_cost = (output_tokens / 1000) * OUTPUT_RATE
                cache_write_cost = (cache_creation / 1000) * CACHE_WRITE_RATE
                cache_read_cost = (cache_read / 1000) * CACHE_READ_RATE
                total_cost = input_cost + output_cost + cache_write_cost + cache_read_cost

                # Extended format: "total|input|output|cost|cache_creation|cache_read"
                token_info = f"{total_tokens}|{input_tokens}|{output_tokens}|{total_cost:.6f}|{cache_creation}|{cache_read}"
                yield ("tokens", token_info)
            yield ("done", None)
            break
