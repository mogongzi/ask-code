"""
Tests for Azure OpenAI provider implementation.
"""

import json
import pytest
from providers import azure
from llm.parsers.azure import AzureResponseParser


class TestAzureBuildPayload:
    """Test azure.build_payload() function."""

    def test_blocking_mode_no_stream(self):
        """In blocking mode (default), payload should NOT include stream field."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages)

        assert "stream" not in payload
        assert "stream_options" not in payload

    def test_streaming_mode_has_stream(self):
        """In streaming mode, payload should include stream: true."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, stream=True)

        assert payload["stream"] is True
        assert payload["stream_options"] == {"include_usage": True}

    def test_max_completion_tokens(self):
        """Should use max_completion_tokens (not max_tokens)."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, max_tokens=4096)

        assert payload["max_completion_tokens"] == 4096
        assert "max_tokens" not in payload

    def test_tools_openai_format(self):
        """Tools should be converted to OpenAI function format."""
        messages = [{"role": "user", "content": "What time is it?"}]
        tools = [
            {
                "name": "get_current_time",
                "description": "Get the current date and time",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "timezone": {"type": "string"},
                        "format": {"type": "string", "enum": ["iso", "human", "unix"]}
                    },
                    "required": []
                }
            }
        ]
        payload = azure.build_payload(messages, tools=tools)

        assert "tools" in payload
        assert len(payload["tools"]) == 1
        tool = payload["tools"][0]
        assert tool["type"] == "function"
        assert tool["function"]["name"] == "get_current_time"
        assert tool["function"]["description"] == "Get the current date and time"
        assert tool["function"]["parameters"]["type"] == "object"

    def test_system_message_added(self):
        """System message should be added as first message with GPT formatting suffix."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, system_prompt="You are helpful.")

        assert payload["messages"][0]["role"] == "system"
        # System prompt should start with our content and include GPT formatting suffix
        content = payload["messages"][0]["content"]
        assert content.startswith("You are helpful.")
        assert "Response Formatting" in content  # GPT formatting suffix appended

    def test_model_optional(self):
        """Model should be omitted when None (proxy handles routing)."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, model=None)

        assert "model" not in payload

    def test_model_included_when_specified(self):
        """Model should be included when specified."""
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, model="gpt-4o")

        assert payload["model"] == "gpt-4o"

    def test_build_payload_places_tools_before_messages(self):
        """Tools should appear before messages in payload (original test)."""
        payload = azure.build_payload(
            messages=[{"role": "user", "content": "Hello"}],
            tools=[{"name": "dummy", "description": "test", "input_schema": {"type": "object"}}],
        )

        keys = list(payload.keys())
        assert "tools" in payload
        assert keys.index("tools") < keys.index("messages")

        messages = payload["messages"]
        assert messages
        assert messages[0]["role"] == "system"


class TestAzureMessageConversion:
    """Test message format conversion for tool calls/results."""

    def test_assistant_tool_use_to_tool_calls(self):
        """Assistant tool_use blocks should convert to OpenAI tool_calls format."""
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call_123",
                        "name": "get_current_time",
                        "input": {"format": "human"}
                    }
                ]
            }
        ]
        payload = azure.build_payload(messages)

        # Find the assistant message (after system message)
        assistant_msg = next(m for m in payload["messages"] if m["role"] == "assistant")
        assert "tool_calls" in assistant_msg
        assert len(assistant_msg["tool_calls"]) == 1
        tc = assistant_msg["tool_calls"][0]
        assert tc["id"] == "call_123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "get_current_time"
        assert tc["function"]["arguments"] == '{"format": "human"}'

    def test_user_tool_result_to_tool_message(self):
        """User tool_result blocks should convert to role:tool messages."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "call_123",
                        "content": "The current time is 3:45 PM"
                    }
                ]
            }
        ]
        payload = azure.build_payload(messages)

        # Find the tool message (after system message)
        tool_msgs = [m for m in payload["messages"] if m["role"] == "tool"]
        assert len(tool_msgs) == 1
        assert tool_msgs[0]["tool_call_id"] == "call_123"
        assert tool_msgs[0]["content"] == "The current time is 3:45 PM"


class TestAzureResponseParser:
    """Test AzureResponseParser with real Azure response format."""

    def test_extract_tool_calls_from_real_response(self):
        """Test parsing tool calls from real Azure response format."""
        # This is the exact format from the user's example
        response = {
            "choices": [
                {
                    "content_filter_results": {},
                    "finish_reason": "tool_calls",
                    "index": 0,
                    "logprobs": None,
                    "message": {
                        "annotations": [],
                        "content": None,
                        "refusal": None,
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "function": {
                                    "arguments": '{"format":"human"}',
                                    "name": "get_current_time"
                                },
                                "id": "call_hCOPLtqd0CUJN9FWciUKqJZf",
                                "type": "function"
                            }
                        ]
                    }
                }
            ],
            "created": 1757581029,
            "id": "chatcmpl-CEXP35m6RvCi5YDtaxnMBaj7f8E3v",
            "model": "gpt-5-2025-08-07",
            "object": "chat.completion",
            "usage": {
                "completion_tokens": 281,
                "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 256,
                    "rejected_prediction_tokens": 0
                },
                "prompt_tokens": 324,
                "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 0
                },
                "total_tokens": 605
            }
        }

        parser = AzureResponseParser()
        tool_calls = parser.extract_tool_calls(response)

        assert len(tool_calls) == 1
        tc = tool_calls[0]
        assert tc["id"] == "call_hCOPLtqd0CUJN9FWciUKqJZf"
        assert tc["name"] == "get_current_time"
        assert tc["input"] == {"format": "human"}

    def test_extract_usage_from_real_response(self):
        """Test parsing usage info from real Azure response."""
        response = {
            "choices": [{"message": {"content": "Hello"}}],
            "usage": {
                "completion_tokens": 281,
                "prompt_tokens": 324,
                "total_tokens": 605
            }
        }

        parser = AzureResponseParser()
        usage = parser.extract_usage(response)

        assert usage.input_tokens == 324
        assert usage.output_tokens == 281
        assert usage.total_tokens == 605

    def test_extract_usage_with_cached_tokens(self):
        """Test parsing usage info with prompt_tokens_details.cached_tokens (Azure/OpenAI format)."""
        response = {
            "choices": [{"message": {"content": "Hello"}}],
            "usage": {
                "completion_tokens": 244,
                "prompt_tokens": 3230,
                "total_tokens": 3474,
                "completion_tokens_details": {
                    "accepted_prediction_tokens": 0,
                    "audio_tokens": 0,
                    "reasoning_tokens": 192,
                    "rejected_prediction_tokens": 0
                },
                "prompt_tokens_details": {
                    "audio_tokens": 0,
                    "cached_tokens": 1408
                }
            }
        }

        parser = AzureResponseParser()
        usage = parser.extract_usage(response)

        assert usage.input_tokens == 3230
        assert usage.output_tokens == 244
        assert usage.total_tokens == 3474
        assert usage.cache_read_input_tokens == 1408
        # Azure doesn't expose cache creation tokens
        assert usage.cache_creation_input_tokens == 0

    def test_extract_usage_without_prompt_details(self):
        """Test that missing prompt_tokens_details doesn't break parsing."""
        response = {
            "choices": [{"message": {"content": "Hello"}}],
            "usage": {
                "completion_tokens": 100,
                "prompt_tokens": 200,
                "total_tokens": 300
            }
        }

        parser = AzureResponseParser()
        usage = parser.extract_usage(response)

        assert usage.input_tokens == 200
        assert usage.output_tokens == 100
        assert usage.cache_read_input_tokens == 0

    def test_extract_text_content(self):
        """Test extracting text content from response."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": "The current time is 3:45 PM",
                        "role": "assistant"
                    }
                }
            ]
        }

        parser = AzureResponseParser()
        text = parser.extract_text(response)

        assert text == "The current time is 3:45 PM"

    def test_extract_text_when_null(self):
        """Text should be empty string when content is null (tool_calls response)."""
        response = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [{"id": "call_123", "function": {"name": "test"}}]
                    }
                }
            ]
        }

        parser = AzureResponseParser()
        text = parser.extract_text(response)

        assert text == ""

    def test_extract_model_name(self):
        """Test extracting model name from response."""
        response = {
            "model": "gpt-5-2025-08-07",
            "choices": [{"message": {"content": "Hi"}}]
        }

        parser = AzureResponseParser()
        model = parser.extract_model_name(response)

        assert model == "gpt-5-2025-08-07"


class TestAzureProviderConstants:
    """Test provider capability constants."""

    def test_no_prompt_caching_support(self):
        """Azure provider should not claim prompt caching support."""
        assert azure.supports_prompt_caching is False
        assert azure.supports_message_cache_control is False

    def test_context_length(self):
        """Context length should be set for usage tracking."""
        assert azure.context_length == 272_000
