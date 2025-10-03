#!/usr/bin/env python3
"""
Test script for blocking client functionality.

This script tests the BlockingClient with mock responses
to verify it correctly handles tool execution and response parsing.
"""

import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from unittest.mock import Mock, patch
from llm.clients import BlockingClient
from llm.types import Provider, LLMResponse
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
    client = BlockingClient(tool_executor=executor, provider=Provider.BEDROCK)

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

    # Mock the requests.post call to return our mock response
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = Mock()

        # Send message
        result = client.send_message("http://test.com/invoke", {"messages": []})

        # Verify result
        assert isinstance(result, LLMResponse)
        print(f"✓ Extracted text: {result.text}")
        assert result.text == "I will use the test tool to analyze this query."

        print(f"✓ Extracted model: {result.model_name}")
        assert result.model_name == "claude-3-sonnet"

        print(f"✓ Extracted {len(result.tool_calls)} tool calls")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "test_tool"
        assert result.tool_calls[0].id == "tool_123"
        assert result.tool_calls[0].result  # Tool was executed

        print(f"✓ Extracted usage: {result.tokens} tokens, ${result.cost:.4f}")
        assert result.tokens == 150

    print("\n✅ Bedrock format parsing successful!\n")


def test_azure_format():
    """Test parsing Azure/OpenAI API response format."""
    print("\n=== Testing Azure/OpenAI Format ===\n")

    # Create client with mock executor
    executor = MockToolExecutor()
    client = BlockingClient(tool_executor=executor, provider=Provider.AZURE)

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

    # Mock the requests.post call to return our mock response
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = Mock()

        # Send message
        result = client.send_message("http://test.com/invoke", {"messages": []})

        # Verify result
        assert isinstance(result, LLMResponse)
        print(f"✓ Extracted text: {result.text}")
        assert result.text == "I will search for the relevant code."

        print(f"✓ Extracted model: {result.model_name}")
        assert result.model_name == "gpt-4"

        print(f"✓ Extracted {len(result.tool_calls)} tool calls")
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "test_tool"
        assert result.tool_calls[0].id == "call_456"
        assert result.tool_calls[0].input["pattern"] == "User.find"

        print(f"✓ Extracted usage: {result.tokens} tokens, ${result.cost:.4f}")
        assert result.tokens == 120

    print("\n✅ Azure/OpenAI format parsing successful!\n")


def test_tool_execution():
    """Test tool execution during response processing."""
    print("\n=== Testing Tool Execution ===\n")

    # Create client with mock executor
    executor = MockToolExecutor()
    client = BlockingClient(tool_executor=executor, provider=Provider.BEDROCK)

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

    # Mock the requests.post call to return our mock response
    with patch('requests.post') as mock_post:
        mock_post.return_value.json.return_value = mock_response
        mock_post.return_value.raise_for_status = Mock()

        # Send message
        result = client.send_message("http://test.com/invoke", {"messages": []})

        # Verify result
        print(f"✓ Executed {len(result.tool_calls)} tool calls")
        assert len(result.tool_calls) == 1

        tool_call = result.tool_calls[0]
        print(f"✓ Tool call ID: {tool_call.id}")
        assert tool_call.id == "tool_789"

        print(f"✓ Tool name: {tool_call.name}")
        assert tool_call.name == "test_tool"

        print(f"✓ Tool result: {tool_call.result}")
        assert "Executed test_tool" in tool_call.result

    print("\n✅ Tool execution successful!\n")


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Blocking Client Test Suite")
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