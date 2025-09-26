"""Tool execution workflow management."""

from typing import List


def process_tool_execution(tool_calls_made: List[dict], conversation,
                          session, use_thinking: bool, tools_enabled: bool,
                          usage, available_tools, format_tool_messages_func, handle_streaming_request_func):
    """Handle the complete tool execution workflow.

    Returns the follow-up StreamResult after tool execution, or None when no tools.
    """
    if not tool_calls_made:
        return None

    # Convert tool calls to conversation messages
    tool_messages = format_tool_messages_func(tool_calls_made)
    conversation.add_tool_messages(tool_messages)

    # Get Claude's response to tool results with live rendering
    result = handle_streaming_request_func(
        session,
        conversation.get_sanitized_history(), use_thinking, tools_enabled,
        available_tools, show_model_name=False
    )

    # Update usage tracking
    usage.update(result.tokens, result.cost)

    # Store Claude's final response
    conversation.add_assistant_message(result.text)

    return result
