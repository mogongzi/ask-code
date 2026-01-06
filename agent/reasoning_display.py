"""
Reasoning display formatter for showing LLM thought process.

This module provides Rich-formatted display of LLM reasoning steps
after the final answer is generated.
"""

import json
from typing import Any, Dict, List

from rich.console import Console
from rich.rule import Rule
from rich.text import Text


def _truncate_text(text: str, max_length: int = 0) -> str:
    """Get first line of text, optionally truncated."""
    if not text:
        return ""
    # Get first line only
    first_line = text.strip().split('\n')[0]
    if max_length > 0 and len(first_line) > max_length:
        return first_line[:max_length - 3] + "..."
    return first_line


def _format_tool_output(output: str, indent: str = "        ") -> str:
    """
    Format tool output for display, preserving structure.

    Args:
        output: Raw tool output (often JSON)
        indent: Indentation prefix for continuation lines

    Returns:
        Formatted output string with proper indentation
    """
    if not output:
        return ""

    output_str = str(output).strip()

    # Try to parse and pretty-print JSON
    try:
        parsed = json.loads(output_str)
        # Pretty print with indentation
        formatted = json.dumps(parsed, indent=2, ensure_ascii=False)
        # Add indent to each line after the first
        lines = formatted.split('\n')
        if len(lines) > 1:
            indented_lines = [lines[0]] + [indent + line for line in lines[1:]]
            return '\n'.join(indented_lines)
        return formatted
    except (json.JSONDecodeError, TypeError):
        # Not JSON, handle as plain text
        lines = output_str.split('\n')
        if len(lines) > 1:
            indented_lines = [lines[0]] + [indent + line for line in lines[1:]]
            return '\n'.join(indented_lines)
        return output_str


def _format_tool_input(tool_input: Dict[str, Any], max_length: int = 0) -> str:
    """Format tool input as compact JSON string."""
    if not tool_input:
        return "{}"
    try:
        compact = json.dumps(tool_input, separators=(',', ':'))
        if max_length > 0 and len(compact) > max_length:
            return compact[:max_length - 3] + "..."
        return compact
    except (TypeError, ValueError):
        result = str(tool_input)
        if max_length > 0 and len(result) > max_length:
            return result[:max_length - 3] + "..."
        return result


def format_complete_reasoning_section(cycles: List[Dict[str, Any]], console: Console) -> None:
    """
    Display complete ReAct cycles in a visually distinct panel.

    Each cycle shows: thought, tool name(s), tool input(s), and tool output(s).
    Supports both single tool calls and parallel tool calls per cycle.

    Args:
        cycles: List of cycle dicts with keys:
            - thought: reasoning content
            - tools: list of {tool_name, tool_input, tool_output} (for parallel calls)
            - tool_name, tool_input, tool_output: single tool (backward compat)
        console: Rich console instance for output
    """
    if not cycles:
        return

    # Build content using Rich Text for colored output
    content = Text()

    for i, cycle in enumerate(cycles, 1):
        # Thought line (first line only, no truncation)
        thought = _truncate_text(cycle.get("thought", ""))
        content.append(f"  ▸ Step {i}: ", style="bold white")
        if thought:
            content.append(f"{thought}\n", style="white")
        else:
            # Tool call without reasoning text from LLM
            content.append("(tool call)\n", style="dim white")

        # Get tools list (support both new parallel format and legacy single tool)
        tools = cycle.get("tools", [])
        if not tools and cycle.get("tool_name"):
            # Backward compatibility: convert single tool to list format
            tools = [{
                "tool_name": cycle.get("tool_name"),
                "tool_input": cycle.get("tool_input"),
                "tool_output": cycle.get("tool_output")
            }]

        # Display each tool
        for tool_idx, tool in enumerate(tools):
            tool_name = tool.get("tool_name")
            if tool_name:
                # Use "Tool" for single tool, "Tool N" for multiple
                prefix = "    Tool" if len(tools) == 1 else f"    Tool {tool_idx + 1}"
                content.append(f"{prefix}: ", style="dim")
                content.append(f"{tool_name}\n", style="cyan")

                # Tool input (full JSON, no truncation)
                tool_input = tool.get("tool_input")
                if tool_input:
                    input_str = _format_tool_input(tool_input)
                    content.append(f"      Input: ", style="dim")
                    content.append(f"{input_str}\n", style="yellow")

                # Tool output (full output with proper formatting)
                tool_output = tool.get("tool_output")
                if tool_output:
                    output_str = _format_tool_output(str(tool_output))
                    content.append(f"      Output: ", style="dim")
                    content.append(f"{output_str}\n", style="green")

        content.append("\n")

    # Display with line separators instead of panel box
    console.print()  # Add spacing
    console.print(Rule("ReAct Trace", style="dim cyan", align="left"))
    console.print(content)
    console.print(Rule(style="dim cyan"))


def format_reasoning_section(reasoning_texts: List[str], console: Console) -> None:
    """
    Display LLM reasoning steps in a visually distinct panel.
    (Legacy function for backward compatibility)

    Args:
        reasoning_texts: List of reasoning text content from THOUGHT steps
        console: Rich console instance for output
    """
    if not reasoning_texts:
        return

    # Build content using Rich Text
    content = Text()

    for i, text in enumerate(reasoning_texts, 1):
        thought = _truncate_text(text)  # First line only, no truncation
        content.append(f"  Step {i}: ", style="bold white")
        content.append(f"{thought}\n\n", style="white")

    # Display with line separators instead of panel box
    console.print()  # Add spacing
    console.print(Rule("LLM Reasoning Trail", style="dim cyan", align="left"))
    console.print(content)
    console.print(Rule(style="dim cyan"))


def get_reasoning_as_markdown(reasoning_texts: List[str]) -> str:
    """
    Format reasoning steps as markdown text (for non-Rich output).

    Args:
        reasoning_texts: List of reasoning text content

    Returns:
        Markdown formatted string
    """
    if not reasoning_texts:
        return ""

    parts = ["\n---\n", "## LLM Reasoning Trail\n"]

    for i, text in enumerate(reasoning_texts, 1):
        first_line = _truncate_text(text)  # First line only
        parts.append(f"**Step {i}:** {first_line}\n")

    return '\n'.join(parts)
