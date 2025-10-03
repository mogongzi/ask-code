"""Test that ToolCall objects work correctly with the fixed code."""

import pytest
from llm.types import ToolCall


def test_toolcall_attribute_access():
    """Test accessing ToolCall object attributes directly (not as dict)."""
    tool_call = ToolCall(
        id="test_id_123",
        name="test_tool",
        input={"param": "value"},
        result="Test result"
    )

    # These should work (attribute access)
    assert tool_call.id == "test_id_123"
    assert tool_call.name == "test_tool"
    assert tool_call.input == {"param": "value"}
    assert tool_call.result == "Test result"

    # This should NOT work (dict access) - would raise AttributeError
    with pytest.raises(AttributeError):
        _ = tool_call.get("name")


def test_toolcall_to_dict():
    """Test converting ToolCall to dict format."""
    tool_call = ToolCall(
        id="test_id_456",
        name="another_tool",
        input={"x": 1},
        result="Another result"
    )

    # Convert to dict
    tool_dict = tool_call.to_dict()

    # Check dict structure
    assert tool_dict == {
        "tool_call": {
            "id": "test_id_456",
            "name": "another_tool",
            "input": {"x": 1}
        },
        "result": "Another result"
    }


def test_toolcall_from_dict():
    """Test creating ToolCall from dict format."""
    tool_dict = {
        "tool_call": {
            "id": "dict_id",
            "name": "dict_tool",
            "input": {"key": "value"}
        },
        "result": "Dict result"
    }

    tool_call = ToolCall.from_dict(tool_dict)

    assert tool_call.id == "dict_id"
    assert tool_call.name == "dict_tool"
    assert tool_call.input == {"key": "value"}
    assert tool_call.result == "Dict result"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
