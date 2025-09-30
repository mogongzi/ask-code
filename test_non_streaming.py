#!/usr/bin/env python3
"""
Test script for non-streaming client functionality.

This script tests the NonStreamingClient with a mock response
to verify it correctly handles tool execution and response parsing.
"""

import json
from non_streaming_client import NonStreamingClient
from tools.executor import ToolExecutor


class MockToolExecutor(ToolExecutor):
    """Mock tool executor for testing."""

    def __init__(self):
        self.tools = {
            "test_tool": lambda **kwargs: {"content": f"Executed test_tool with {kwargs}"}
        }

    def execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a mock tool."""
        if tool_name in self.tools:
            result = self.tools[tool_name](**tool_input)
            return result
        return {"error": f"Tool {tool_name} not found"}


def test_bedrock_format():
    """Test parsing Bedrock API response format."""
    print("\n=== Testing Bedrock Format ===\n")

    # Create client with mock executor
    executor = MockToolExecutor()
    client = NonStreamingClient(tool_executor=executor)

    # Mock Bedrock response (actual format from /invoke endpoint)
    mock_response = {
        "id": "msg_bdrk_123",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-sonnet",
        "content": [
            {
                "type": "text",
                "text": "I will use the test tool to analyze this query."
            },
            {
                "type": "tool_use",
                "id": "tool_123",
                "name": "test_tool",
                "input": {"query": "SELECT * FROM users"}
            }
        ],
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    }

    # Extract components
    text = client._extract_text(mock_response, "bedrock")
    print(f"✓ Extracted text: {text}")
    assert text == "I will use the test tool to analyze this query."

    model = client._extract_model_name(mock_response, "bedrock")
    print(f"✓ Extracted model: {model}")
    assert model == "claude-3-sonnet"

    tool_calls = client._extract_tool_calls(mock_response, "bedrock")
    print(f"✓ Extracted {len(tool_calls)} tool calls")
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "test_tool"
    assert tool_calls[0]["id"] == "tool_123"

    tokens, cost = client._extract_usage(mock_response, "bedrock")
    print(f"✓ Extracted usage: {tokens} tokens, ${cost:.4f}")
    assert tokens == 150

    print("\n✅ Bedrock format parsing successful!\n")


def test_azure_format():
    """Test parsing Azure/OpenAI API response format."""
    print("\n=== Testing Azure/OpenAI Format ===\n")

    # Create client with mock executor
    executor = MockToolExecutor()
    client = NonStreamingClient(tool_executor=executor)

    # Mock Azure/OpenAI response
    mock_response = {
        "id": "chatcmpl-123",
        "model": "gpt-4",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "I will search for the relevant code.",
                    "tool_calls": [
                        {
                            "id": "call_456",
                            "type": "function",
                            "function": {
                                "name": "test_tool",
                                "arguments": json.dumps({"pattern": "User.find"})
                            }
                        }
                    ]
                }
            }
        ],
        "usage": {
            "prompt_tokens": 80,
            "completion_tokens": 40,
            "total_tokens": 120
        }
    }

    # Extract components
    text = client._extract_text(mock_response, "azure")
    print(f"✓ Extracted text: {text}")
    assert text == "I will search for the relevant code."

    model = client._extract_model_name(mock_response, "azure")
    print(f"✓ Extracted model: {model}")
    assert model == "gpt-4"

    tool_calls = client._extract_tool_calls(mock_response, "azure")
    print(f"✓ Extracted {len(tool_calls)} tool calls")
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "test_tool"
    assert tool_calls[0]["id"] == "call_456"
    assert tool_calls[0]["input"]["pattern"] == "User.find"

    tokens, cost = client._extract_usage(mock_response, "azure")
    print(f"✓ Extracted usage: {tokens} tokens, ${cost:.4f}")
    assert tokens == 120

    print("\n✅ Azure/OpenAI format parsing successful!\n")


def test_tool_execution():
    """Test tool execution during response processing."""
    print("\n=== Testing Tool Execution ===\n")

    # Create client with mock executor
    executor = MockToolExecutor()
    client = NonStreamingClient(tool_executor=executor)

    # Mock response with tool calls (actual Bedrock format)
    mock_response = {
        "id": "msg_bdrk_789",
        "type": "message",
        "role": "assistant",
        "model": "claude-3-sonnet",
        "content": [
            {
                "type": "tool_use",
                "id": "tool_789",
                "name": "test_tool",
                "input": {"action": "search", "query": "User model"}
            }
        ],
        "stop_reason": "tool_use",
        "usage": {
            "input_tokens": 50,
            "output_tokens": 25
        }
    }

    # Execute tool calls
    tool_results = client._execute_tool_calls(mock_response, "bedrock")

    print(f"✓ Executed {len(tool_results)} tool calls")
    assert len(tool_results) == 1

    result = tool_results[0]
    print(f"✓ Tool call ID: {result['tool_call']['id']}")
    assert result['tool_call']['id'] == "tool_789"

    print(f"✓ Tool name: {result['tool_call']['name']}")
    assert result['tool_call']['name'] == "test_tool"

    print(f"✓ Tool result: {result['result']}")
    assert "Executed test_tool" in result['result']

    print("\n✅ Tool execution successful!\n")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Non-Streaming Client Test Suite")
    print("="*60)

    try:
        test_bedrock_format()
        test_azure_format()
        test_tool_execution()

        print("\n" + "="*60)
        print("  ✅ ALL TESTS PASSED!")
        print("="*60 + "\n")
        return 0

    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())