from __future__ import annotations

import json
from typing import Dict, Iterator, Optional, Tuple, List


Event = Tuple[str, Optional[str]]  # ("model"|"text"|"thinking"|"tool_start"|"tool_input_delta"|"tool_ready"|"done"|"tokens", value)

# Bedrock Anthropic does not support prompt caching yet.
supports_prompt_caching = False


def build_payload(
    messages: List[dict], *, model: Optional[str] = None, max_tokens: int = 4096, temperature: Optional[float] = None, thinking: bool = False, thinking_tokens: int = 1024, tools: Optional[List[dict]] = None, system_prompt: Optional[str] = None, stop_sequences: Optional[List[str]] = None, **_: dict
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
    if system_prompt:
        payload["system"] = system_prompt

    # Messages come after system prompt
    payload["messages"] = processed_messages

    if thinking:
        payload["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_tokens
        }

    if tools:
        payload["tools"] = tools

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
            # Extract token usage and cost if available
            usage = evt.get("amazon-bedrock-invocationMetrics") or evt.get("usage")
            if usage:
                input_tokens = usage.get("inputTokenCount", 0) or usage.get("input_tokens", 0)
                output_tokens = usage.get("outputTokenCount", 0) or usage.get("output_tokens", 0)
                total_tokens = input_tokens + output_tokens
                if total_tokens > 0:
                    # Calculate cost (Claude 4 Sonnet pricing: $2.04/1K input, $9.88/1K output)
                    input_cost = (input_tokens / 1000) * 0.00204
                    output_cost = (output_tokens / 1000) * 0.00988
                    total_cost = input_cost + output_cost

                    # Format: "tokens|input_tokens|output_tokens|cost"
                    token_info = f"{total_tokens}|{input_tokens}|{output_tokens}|{total_cost:.6f}"
                    yield ("tokens", token_info)
            yield ("done", None)
            break
