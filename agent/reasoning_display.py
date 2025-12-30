"""
Reasoning display formatter for showing LLM thought process.

This module provides Rich-formatted display of LLM reasoning steps
after the final answer is generated.
"""

import json
from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich import box


def _truncate_text(text: str, max_length: int = 0) -> str:
    """Get first line of text, optionally truncated."""
    if not text:
        return ""
    # Get first line only
    first_line = text.strip().split('\n')[0]
    if max_length > 0 and len(first_line) > max_length:
        return first_line[:max_length - 3] + "..."
    return first_line


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

    Each cycle shows: thought, tool name, tool input, and tool output.

    Args:
        cycles: List of cycle dicts with keys: thought, tool_name, tool_input, tool_output
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
        content.append(f"{thought}\n", style="white")

        # Tool info (if present)
        tool_name = cycle.get("tool_name")
        if tool_name:
            content.append(f"    Tool: ", style="dim")
            content.append(f"{tool_name}\n", style="cyan")

            # Tool input (full JSON, no truncation)
            tool_input = cycle.get("tool_input")
            if tool_input:
                input_str = _format_tool_input(tool_input)
                content.append(f"    Input: ", style="dim")
                content.append(f"{input_str}\n", style="yellow")

            # Tool output (first line only, no truncation)
            tool_output = cycle.get("tool_output")
            if tool_output:
                output_str = _truncate_text(str(tool_output))
                content.append(f"    Output: ", style="dim")
                content.append(f"{output_str}\n", style="green")

        content.append("\n")

    # Create panel with distinct styling
    panel = Panel(
        content,
        title="[bold cyan]ReAct Trace[/bold cyan]",
        title_align="left",
        border_style="dim cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )

    console.print()  # Add spacing
    console.print(panel)


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

    # Create panel with distinct styling
    panel = Panel(
        content,
        title="[bold cyan]LLM Reasoning Trail[/bold cyan]",
        title_align="left",
        border_style="dim cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    )

    console.print()  # Add spacing
    console.print(panel)


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
