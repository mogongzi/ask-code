from __future__ import annotations

import json
from typing import Dict, Iterator, List, Optional, Tuple

Event = Tuple[str, Optional[str]]  # ("model"|"text"|"tool_start"|"tool_input_delta"|"tool_ready"|"done"|"tokens", value)

# Approximate maximum context window for the default Azure/OpenAI config used here.
# GPT-5 example configuration supports ~272k tokens context.
# Exposed so the CLI can size its usage indicator appropriately.
context_length: int = 272_000

def _build_openai_tools(tools: List[dict]) -> List[dict]:
    """Build OpenAI tools array from tool definitions.

    Takes abstract tool definitions and constructs OpenAI-specific format.
    """
    openai_tools = []
    for tool in tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        })
    return openai_tools

def _build_openai_messages(messages: List[dict]) -> List[dict]:
    """Build OpenAI messages array from message history.

    Handles message format differences for OpenAI API.
    """
    openai_messages = []

    for message in messages:
        role = message.get("role")
        content = message.get("content")

        if role == "assistant" and isinstance(content, list):
            # Assistant message with structured content
            tool_calls = []
            text_content = ""

            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_calls.append({
                        "id": block["id"],
                        "type": "function",
                        "function": {
                            "name": block["name"],
                            "arguments": json.dumps(block["input"])
                        }
                    })
                elif isinstance(block, dict) and block.get("type") == "text":
                    text_content += block.get("text", "")
                elif isinstance(block, str):
                    text_content += block

            openai_message = {"role": "assistant"}
            if text_content:
                openai_message["content"] = text_content
            if tool_calls:
                openai_message["tool_calls"] = tool_calls
                if not text_content:
                    openai_message["content"] = None

            openai_messages.append(openai_message)

        elif role == "user" and isinstance(content, list):
            # User message with structured content
            has_tool_results = any(
                isinstance(block, dict) and block.get("type") == "tool_result"
                for block in content
            )

            if has_tool_results:
                # Convert tool results to separate tool messages
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        openai_messages.append({
                            "role": "tool",
                            "tool_call_id": block["tool_use_id"],
                            "content": block["content"]
                        })
            else:
                # Regular user message
                text_content = ""
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_content += block.get("text", "")
                    elif isinstance(block, str):
                        text_content += block

                openai_messages.append({
                    "role": "user",
                    "content": text_content or content
                })
        else:
            # Standard message format
            openai_messages.append(message)

    return openai_messages

def build_payload(
    messages: List[dict], *, model: Optional[str] = None, max_tokens: Optional[int] = None, temperature: Optional[float] = None, thinking: bool = False, tools: Optional[List[dict]] = None, context_content: Optional[str] = None, **_: dict
) -> dict:
    """Construct an Azure/OpenAI Chat Completions streaming payload.

    Requires `model`. Includes `stream: true`.

    Args:
        messages: List of conversation messages (any format)
        model: Model name (e.g., "gpt-4o")
        max_tokens: Maximum completion tokens
        temperature: Sampling temperature
        thinking: Enable reasoning mode (adds reasoning_effort and verbosity params)
        tools: List of tool definitions (abstract format)

    Returns:
        OpenAI-compatible request payload
    """
    # Build OpenAI-compatible messages
    openai_messages = _build_openai_messages(messages)

    # Add system prompt if not already present
    final_messages = openai_messages.copy()
    if not openai_messages or openai_messages[0].get("role") != "system":
        system_message = {"role": "system", "content": "Use Markdown formatting when appropriate."}
        final_messages.insert(0, system_message)

    # Optionally inject context by prepending to the first user message content
    if context_content and context_content.strip():
        inserted = False
        for msg in final_messages:
            if msg.get("role") == "user":
                old = msg.get("content")
                if isinstance(old, str) and old:
                    msg["content"] = f"{context_content}\n\n{old}"
                elif old is None:
                    msg["content"] = context_content
                elif isinstance(old, str) and not old:
                    msg["content"] = context_content
                else:
                    # Fallback: insert a new user message before this
                    idx = final_messages.index(msg)
                    final_messages.insert(idx, {"role": "user", "content": context_content})
                inserted = True
                break
        if not inserted:
            # No user message found; place after system message if present, else as first
            if final_messages and final_messages[0].get("role") == "system":
                final_messages.insert(1, {"role": "user", "content": context_content})
            else:
                final_messages.insert(0, {"role": "user", "content": context_content})

    body: Dict = {
        "stream": True,
        "stream_options": {
            "include_usage": True
        }
    }

    # Add reasoning parameters only when thinking mode is enabled
    if thinking:
        body["reasoning_effort"] = "medium"
        body["verbosity"] = "medium"
    if model is not None:
        body["model"] = model
    if max_tokens is not None:
        body["max_completion_tokens"] = max_tokens
    if temperature is not None:
        body["temperature"] = temperature
    if tools:
        body["tools"] = _build_openai_tools(tools)

    body["messages"] = final_messages
    return body


def map_events(lines: Iterator[str]) -> Iterator[Event]:
    """Map Azure/OpenAI Chat Completions SSE chunks to unified events.

    Emits:
    - ("model", name) on first chunk carrying `model`
    - ("text", delta) for each `choices[0].delta.content` string
    - ("tool_start", tool_info_json) on tool_calls start
    - ("tool_input_delta", partial_json) on tool_calls function.arguments delta
    - ("tool_ready", None) when tool call is complete
    - ("tokens", token_count_str) on completion with usage info
    - ("done", None) on `[DONE]` or when a `finish_reason` is observed
    """
    sent_model = False
    current_tool_calls = {}  # Track ongoing tool calls by index
    accumulated_text = ""  # Track text for fallback token estimation
    has_finished = False  # Track if we've seen a finish_reason

    for data in lines:
        if data == "[DONE]":
            yield ("done", None)
            break
        try:
            evt: Dict = json.loads(data)
        except json.JSONDecodeError:
            continue

        model = evt.get("model")
        if not sent_model and isinstance(model, str) and model:
            yield ("model", model)
            sent_model = True

        choices = evt.get("choices") or []
        for ch in choices:
            delta = ch.get("delta") or {}
            content = delta.get("content")
            if isinstance(content, str) and content:
                accumulated_text += content
                yield ("text", content)

            # Handle tool calls in OpenAI streaming format
            tool_calls = delta.get("tool_calls")
            if tool_calls:
                for tool_call in tool_calls:
                    index = tool_call.get("index", 0)
                    tool_id = tool_call.get("id")
                    function = tool_call.get("function") or {}

                    # Initialize tool call tracking if new
                    if index not in current_tool_calls:
                        name = function.get("name", "")
                        if tool_id and name:
                            current_tool_calls[index] = {
                                "id": tool_id,
                                "name": name,
                                "arguments": ""
                            }
                            # Emit tool start event
                            yield ("tool_start", json.dumps({
                                "id": tool_id,
                                "name": name
                            }))

                    # Accumulate function arguments
                    arguments = function.get("arguments", "")
                    if arguments and index in current_tool_calls:
                        current_tool_calls[index]["arguments"] += arguments
                        yield ("tool_input_delta", arguments)

        # Check for tool completion first
        for ch in choices:
            finish_reason = ch.get("finish_reason")
            if finish_reason == "tool_calls" and current_tool_calls:
                for tool_call in current_tool_calls.values():
                    yield ("tool_ready", None)
                # Don't emit done here, let the tool execution complete
                return

        # Extract token usage and cost if available
        usage = evt.get("usage")
        if usage:
            total_tokens = usage.get("total_tokens", 0)
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            if total_tokens > 0:
                # Calculate cost (GPT-5 pricing: $0.91/1K input, $6.77/1K output)
                input_cost = (input_tokens / 1000) * 0.00091
                output_cost = (output_tokens / 1000) * 0.00677
                total_cost = input_cost + output_cost

                # Format: "tokens|input_tokens|output_tokens|cost"
                token_info = f"{total_tokens}|{input_tokens}|{output_tokens}|{total_cost:.6f}"
                yield ("tokens", token_info)

                # If we had a previous finish_reason, now emit done after getting usage
                if has_finished:
                    yield ("done", None)
                    return

        # Check for completion - set flag but don't emit done yet (wait for usage)
        for ch in choices:
            finish_reason = ch.get("finish_reason")
            if finish_reason is not None:
                has_finished = True
                # If we already have usage data in this same chunk, emit done now
                if usage:
                    yield ("done", None)
                    return
                # Otherwise, wait for the next chunk with usage data
                break

        # Handle case where we finished but no usage data comes (fallback estimation)
        # This happens if we've finished and processed several chunks without usage
        if has_finished and not usage and len(choices) == 0:
            # This is likely the final empty chunk, trigger fallback
            if accumulated_text:
                estimated_output_tokens = max(1, len(accumulated_text.split()) * 1.3)
                estimated_input_tokens = 10
                estimated_total_tokens = int(estimated_input_tokens + estimated_output_tokens)

                input_cost = (estimated_input_tokens / 1000) * 0.00091
                output_cost = (estimated_output_tokens / 1000) * 0.00677
                total_cost = input_cost + output_cost

                token_info = f"~{estimated_total_tokens}|~{estimated_input_tokens}|~{int(estimated_output_tokens)}|{total_cost:.6f}"
                yield ("tokens", token_info)

            yield ("done", None)
            return

    # Handle end of stream - if we had a finish_reason but never got usage data
    if has_finished:
        if accumulated_text:
            estimated_output_tokens = max(1, len(accumulated_text.split()) * 1.3)
            estimated_input_tokens = 10
            estimated_total_tokens = int(estimated_input_tokens + estimated_output_tokens)

            input_cost = (estimated_input_tokens / 1000) * 0.00091
            output_cost = (estimated_output_tokens / 1000) * 0.00677
            total_cost = input_cost + output_cost

            token_info = f"~{estimated_total_tokens}|~{estimated_input_tokens}|~{int(estimated_output_tokens)}|{total_cost:.6f}"
            yield ("tokens", token_info)

        yield ("done", None)
