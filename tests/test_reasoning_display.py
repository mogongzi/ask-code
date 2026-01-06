"""
Tests for agent.reasoning_display module.
"""

import pytest
from io import StringIO
from rich.console import Console

from agent.reasoning_display import (
    format_complete_reasoning_section,
    format_reasoning_section,
    get_reasoning_as_markdown,
    _truncate_text,
    _format_tool_input,
    _format_tool_output,
)


class TestTruncateText:
    """Test suite for _truncate_text helper function."""

    def test_no_truncation_by_default(self):
        """Test that text is not truncated when max_length=0."""
        result = _truncate_text("this is a long text that should not be truncated")
        assert result == "this is a long text that should not be truncated"

    def test_truncate_when_max_length_set(self):
        """Test that long text is truncated when max_length is set."""
        result = _truncate_text("this is a very long text that should be truncated", 20)
        assert len(result) == 20
        assert result.endswith("...")

    def test_multiline_keeps_first_line(self):
        """Test that only first line is kept."""
        result = _truncate_text("first line\nsecond line\nthird line")
        assert result == "first line"
        assert "\n" not in result

    def test_empty_string(self):
        """Test empty string returns empty."""
        result = _truncate_text("")
        assert result == ""

    def test_none_returns_empty(self):
        """Test None returns empty string."""
        result = _truncate_text(None)
        assert result == ""


class TestFormatToolInput:
    """Test suite for _format_tool_input helper function."""

    def test_format_simple_dict(self):
        """Test formatting simple dictionary."""
        result = _format_tool_input({"pattern": "test"})
        assert result == '{"pattern":"test"}'

    def test_format_empty_dict(self):
        """Test formatting empty dictionary."""
        result = _format_tool_input({})
        assert result == "{}"

    def test_format_none(self):
        """Test formatting None."""
        result = _format_tool_input(None)
        assert result == "{}"

    def test_no_truncation_by_default(self):
        """Test that input is not truncated when max_length=0."""
        long_input = {"very_long_key": "very_long_value_that_should_not_be_truncated"}
        result = _format_tool_input(long_input)
        assert "very_long_value_that_should_not_be_truncated" in result

    def test_truncate_when_max_length_set(self):
        """Test that long input is truncated when max_length is set."""
        long_input = {"very_long_key": "very_long_value_that_should_be_truncated"}
        result = _format_tool_input(long_input, 30)
        assert len(result) == 30
        assert result.endswith("...")


class TestFormatToolOutput:
    """Test suite for _format_tool_output helper function."""

    def test_format_json_output(self):
        """Test formatting JSON output with pretty printing."""
        json_output = '{"matches": [{"file": "test.rb", "line": 10}]}'
        result = _format_tool_output(json_output)
        # Should be pretty-printed
        assert "matches" in result
        assert "test.rb" in result
        # Should have newlines for multi-line JSON
        assert "\n" in result

    def test_format_nested_json(self):
        """Test formatting nested JSON preserves structure."""
        json_output = '{"results": {"count": 5, "items": ["a", "b", "c"]}}'
        result = _format_tool_output(json_output)
        assert "results" in result
        assert "count" in result
        assert "items" in result

    def test_format_plain_text(self):
        """Test formatting plain text output."""
        plain_output = "Found 5 matches in test.rb"
        result = _format_tool_output(plain_output)
        assert result == "Found 5 matches in test.rb"

    def test_format_multiline_plain_text(self):
        """Test formatting multiline plain text with indentation."""
        multiline = "Line 1\nLine 2\nLine 3"
        result = _format_tool_output(multiline)
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        # Continuation lines should be indented
        lines = result.split('\n')
        assert len(lines) == 3
        assert lines[1].startswith("        ")  # Default indent

    def test_format_empty_output(self):
        """Test formatting empty output."""
        result = _format_tool_output("")
        assert result == ""

    def test_format_none_output(self):
        """Test formatting None output."""
        result = _format_tool_output(None)
        assert result == ""

    def test_format_custom_indent(self):
        """Test custom indentation for continuation lines."""
        multiline = "Line 1\nLine 2"
        result = _format_tool_output(multiline, indent="  ")
        lines = result.split('\n')
        assert lines[1].startswith("  ")


class TestFormatCompleteReasoningSection:
    """Test suite for format_complete_reasoning_section function."""

    def test_format_empty_cycles(self):
        """Test that empty cycles list produces no output."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        format_complete_reasoning_section([], console)

        result = output.getvalue()
        assert "ReAct Trace" not in result

    def test_format_single_complete_cycle(self):
        """Test formatting a single complete cycle."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=100)

        cycles = [{
            "thought": "Let me search for the model",
            "tool_name": "ripgrep",
            "tool_input": {"pattern": "User"},
            "tool_output": "Found 5 matches"
        }]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "ReAct Trace" in result
        assert "Step 1" in result
        assert "ripgrep" in result

    def test_format_cycle_without_tool(self):
        """Test formatting cycle without tool (thought only)."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=100)

        cycles = [{"thought": "Just thinking about this"}]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "ReAct Trace" in result
        assert "Step 1" in result

    def test_format_multiple_cycles(self):
        """Test formatting multiple cycles."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=100)

        cycles = [
            {
                "thought": "First thought",
                "tool_name": "tool1",
                "tool_input": {"arg": "val1"},
                "tool_output": "Result 1"
            },
            {
                "thought": "Second thought",
                "tool_name": "tool2",
                "tool_input": {"arg": "val2"},
                "tool_output": "Result 2"
            }
        ]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "Step 1" in result
        assert "Step 2" in result

    def test_format_parallel_tool_calls(self):
        """Test formatting cycles with multiple parallel tool calls."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)

        cycles = [{
            "thought": "Search for patterns",
            "tools": [
                {"tool_name": "ripgrep", "tool_input": {"pattern": "test"}, "tool_output": "Found 3 matches"},
                {"tool_name": "ast_grep", "tool_input": {"pattern": "$_"}, "tool_output": "Found 1 match"}
            ],
            # Backward compatibility fields
            "tool_name": "ripgrep",
            "tool_input": {"pattern": "test"},
            "tool_output": "Found 3 matches"
        }]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "ReAct Trace" in result
        assert "Step 1" in result
        # Multiple tools should show "Tool 1", "Tool 2"
        assert "Tool 1" in result
        assert "Tool 2" in result
        assert "ripgrep" in result
        assert "ast_grep" in result

    def test_format_single_tool_no_numbering(self):
        """Test that single tool shows 'Tool:' without numbering."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)

        cycles = [{
            "thought": "Search for model",
            "tools": [
                {"tool_name": "ripgrep", "tool_input": {"pattern": "User"}, "tool_output": "Found match"}
            ],
            "tool_name": "ripgrep",
            "tool_input": {"pattern": "User"},
            "tool_output": "Found match"
        }]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        # Single tool should NOT have "Tool 1" numbering
        assert "Tool:" in result or "Tool: " in result
        assert "Tool 1" not in result

    def test_format_legacy_single_tool_format(self):
        """Test backward compatibility with legacy single-tool format (no tools array)."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)

        # Legacy format without 'tools' array
        cycles = [{
            "thought": "Search for model",
            "tool_name": "ripgrep",
            "tool_input": {"pattern": "User"},
            "tool_output": "Found match"
        }]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "ReAct Trace" in result
        assert "ripgrep" in result
        assert "Tool:" in result or "Tool: " in result

    def test_format_orphaned_tool_call(self):
        """Test display of tool call without reasoning text (empty thought)."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)

        # Cycle with empty thought (orphaned tool call)
        cycles = [{
            "thought": "",  # Empty - LLM made tool call without reasoning
            "tools": [
                {"tool_name": "ripgrep", "tool_input": {"pattern": "User"}, "tool_output": "Found 5 matches"}
            ],
            "tool_name": "ripgrep",
            "tool_input": {"pattern": "User"},
            "tool_output": "Found 5 matches"
        }]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "ReAct Trace" in result
        assert "Step 1" in result
        assert "(tool call)" in result  # Placeholder for empty thought
        assert "ripgrep" in result

    def test_format_mixed_thought_and_orphaned(self):
        """Test display with mix of cycles with and without thought."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=120)

        cycles = [
            {
                "thought": "Let me search for the model",
                "tools": [{"tool_name": "ripgrep", "tool_input": {"p": "1"}, "tool_output": "Result 1"}],
                "tool_name": "ripgrep", "tool_input": {"p": "1"}, "tool_output": "Result 1"
            },
            {
                "thought": "",  # Orphaned
                "tools": [{"tool_name": "file_reader", "tool_input": {"path": "x"}, "tool_output": "Content"}],
                "tool_name": "file_reader", "tool_input": {"path": "x"}, "tool_output": "Content"
            },
            {
                "thought": "Now I understand",
                "tools": [{"tool_name": "model_analyzer", "tool_input": {"m": "U"}, "tool_output": "Info"}],
                "tool_name": "model_analyzer", "tool_input": {"m": "U"}, "tool_output": "Info"
            }
        ]
        format_complete_reasoning_section(cycles, console)

        result = output.getvalue()
        assert "Step 1" in result
        assert "Step 2" in result
        assert "Step 3" in result
        assert "Let me search" in result
        assert "(tool call)" in result  # Step 2 has empty thought
        assert "Now I understand" in result


class TestFormatReasoningSection:
    """Test suite for format_reasoning_section function (legacy)."""

    def test_format_reasoning_section_empty(self):
        """Test that empty reasoning list produces no output."""
        output = StringIO()
        console = Console(file=output, force_terminal=True)

        format_reasoning_section([], console)

        result = output.getvalue()
        assert "LLM Reasoning Trail" not in result

    def test_format_reasoning_section_single(self):
        """Test formatting single reasoning step."""
        output = StringIO()
        console = Console(file=output, force_terminal=True, width=100)

        format_reasoning_section(["Let me search for the model"], console)

        result = output.getvalue()
        assert "LLM Reasoning Trail" in result
        assert "Step 1" in result


class TestGetReasoningAsMarkdown:
    """Test suite for get_reasoning_as_markdown function."""

    def test_get_reasoning_as_markdown_empty(self):
        """Test empty reasoning returns empty string."""
        result = get_reasoning_as_markdown([])
        assert result == ""

    def test_get_reasoning_as_markdown_single(self):
        """Test formatting single reasoning step as markdown."""
        result = get_reasoning_as_markdown(["First thought"])

        assert "## LLM Reasoning Trail" in result
        assert "**Step 1:**" in result
        assert "First thought" in result

    def test_get_reasoning_as_markdown_multiple(self):
        """Test formatting multiple reasoning steps as markdown."""
        reasoning = ["First thought", "Second thought", "Third thought"]
        result = get_reasoning_as_markdown(reasoning)

        assert "## LLM Reasoning Trail" in result
        assert "**Step 1:**" in result
        assert "**Step 2:**" in result
        assert "**Step 3:**" in result

    def test_get_reasoning_as_markdown_contains_separator(self):
        """Test that markdown output contains separator."""
        result = get_reasoning_as_markdown(["Thought"])

        assert "---" in result
