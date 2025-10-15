"""
Test prompt caching for transaction_analyzer tool results.

Verifies that transaction_analyzer results are marked with cache_control
to reduce token costs in multi-turn agent conversations.
"""

import json
from unittest.mock import MagicMock, Mock

from agent.llm_client import LLMClient
from llm.types import ToolCall


def test_transaction_analyzer_result_has_cache_control():
    """Verify transaction_analyzer tool results include cache_control metadata."""
    # Create mock LLM client
    client = LLMClient()

    # Create mock ToolCall for transaction_analyzer
    tool_call = ToolCall(
        id="toolu_test123",
        name="transaction_analyzer",
        input={"transaction_log": "BEGIN; INSERT INTO users..."},
        result=json.dumps({
            "transaction_summary": "Test transaction analysis",
            "query_count": 5,
            "tables_affected": ["users", "audit_logs"],
            "_metadata": {"cacheable": True}
        })
    )

    # Format tool messages
    messages = client.format_tool_messages([tool_call])

    # Verify structure: [assistant message, user message]
    assert len(messages) == 2
    assert messages[0]["role"] == "assistant"
    assert messages[1]["role"] == "user"

    # Verify tool_result has cache_control
    tool_result_blocks = messages[1]["content"]
    assert len(tool_result_blocks) == 1

    tool_result = tool_result_blocks[0]
    assert tool_result["type"] == "tool_result"
    assert tool_result["tool_use_id"] == "toolu_test123"
    assert "cache_control" in tool_result
    assert tool_result["cache_control"] == {"type": "ephemeral"}


def test_other_tools_do_not_have_cache_control():
    """Verify only transaction_analyzer results get cache_control, not other tools."""
    client = LLMClient()

    # Create mock ToolCall for ripgrep_tool (should NOT have cache_control)
    tool_call = ToolCall(
        id="toolu_test456",
        name="ripgrep_tool",
        input={"pattern": "after_create"},
        result=json.dumps({"matches": ["app/models/user.rb:15"]})
    )

    # Format tool messages
    messages = client.format_tool_messages([tool_call])

    # Verify tool_result does NOT have cache_control
    tool_result = messages[1]["content"][0]
    assert tool_result["type"] == "tool_result"
    assert "cache_control" not in tool_result


def test_multiple_tool_calls_with_mixed_caching():
    """Verify caching is applied correctly when multiple tools are called."""
    client = LLMClient()

    # Create mixed tool calls
    tool_calls = [
        ToolCall(
            id="toolu_001",
            name="ripgrep_tool",
            input={"pattern": "callback"},
            result='{"matches": []}'
        ),
        ToolCall(
            id="toolu_002",
            name="transaction_analyzer",
            input={"transaction_log": "BEGIN; ..."},
            result='{"transaction_summary": "Analysis", "_metadata": {"cacheable": true}}'
        ),
        ToolCall(
            id="toolu_003",
            name="model_analyzer",
            input={"model_name": "User"},
            result='{"callbacks": ["after_create"]}'
        ),
    ]

    # Format tool messages
    messages = client.format_tool_messages(tool_calls)

    # Verify only transaction_analyzer has cache_control
    tool_results = messages[1]["content"]
    assert len(tool_results) == 3

    # First tool (ripgrep): no cache_control
    assert "cache_control" not in tool_results[0]

    # Second tool (transaction_analyzer): has cache_control
    assert tool_results[1]["cache_control"] == {"type": "ephemeral"}

    # Third tool (model_analyzer): no cache_control
    assert "cache_control" not in tool_results[2]


def test_transaction_analyzer_metadata_structure():
    """Verify transaction_analyzer returns proper _metadata field."""
    from tools.transaction_analyzer import TransactionAnalyzer

    # Create analyzer with mock project root
    analyzer = TransactionAnalyzer(project_root="/tmp/test_project")

    # Simple transaction log
    transaction_log = """
    2025-10-14T10:00:00.000Z 123 Query BEGIN
    2025-10-14T10:00:00.001Z 123 Query INSERT INTO users (name, email) VALUES ('Alice', 'alice@example.com')
    2025-10-14T10:00:00.002Z 123 Query COMMIT
    """

    # Execute analysis
    result = analyzer.execute({
        "transaction_log": transaction_log,
        "find_source_code": False  # Skip source search for unit test
    })

    # Verify result structure
    assert "error" not in result
    assert "_metadata" in result
    assert result["_metadata"]["cacheable"] is True
    assert "cache_reason" in result["_metadata"]
    assert "transaction_summary" in result


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
