"""
Explored Display Renderer

Renders a Codex-style "Explored" section showing tool executions
with tree structure and live updates.

Example output:
• Explored
  └ Search FROM `members` WHERE `members`.`id` IN in .
    Search default_scope in member.rb
    Read action_item.rb, expert_tag.rb, feed_filter.rb
    List ls -la
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Dict, List, Optional

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from agent.exploration_tracker import ExplorationTracker, ExploredItem, ExploredType


# Tree structure prefixes
FIRST_PREFIX = "  └ "  # 2 spaces + └ + space
SUBSEQUENT_PREFIX = "    "  # 4 spaces


class ExploredDisplay:
    """
    Renders exploration tracking with Codex-style tree structure.

    Supports:
    - Live updates during exploration (◦ Exploring with spinner)
    - Completed state (• Explored)
    - Tree-like indentation with └ for first item
    - Grouping of consecutive Read operations
    - Cyan-colored operation types
    - Fade-in animation for new items
    """

    def __init__(self, console: Console):
        self.console = console
        self.live: Optional[Live] = None
        self._last_render: Optional[str] = None
        self._fade_items: Dict[int, float] = {}  # item_index -> start_time
        self._fade_duration = 0.3  # seconds
        self._tracker: Optional["ExplorationTracker"] = None

    def _get_item_style(self, item_index: int) -> str:
        """
        Get style for item based on fade progress (dim → normal).

        Args:
            item_index: Index of the item in the grouped items list

        Returns:
            Style string ("dim" for new items, "" for fully visible)
        """
        if item_index not in self._fade_items:
            return ""

        elapsed = time.time() - self._fade_items[item_index]
        if elapsed >= self._fade_duration:
            # Fade complete, remove from tracking
            del self._fade_items[item_index]
            return ""

        # Items start dim and fade to normal
        progress = elapsed / self._fade_duration
        return "dim" if progress < 0.5 else ""

    def _format_item(self, item: "ExploredItem", is_first: bool, extra_style: str = "") -> Text:
        """
        Format a single exploration item.

        Args:
            item: The ExploredItem to format
            is_first: Whether this is the first item (uses └ prefix)
            extra_style: Optional extra style for animation (e.g., "dim" for fade-in)

        Returns:
            Rich Text object with formatted item
        """
        from agent.exploration_tracker import ExploredType

        prefix = FIRST_PREFIX if is_first else SUBSEQUENT_PREFIX
        text = Text()
        text.append(prefix, style="dim")

        # Operation type in cyan (with optional fade style)
        type_style = f"cyan {extra_style}".strip() if extra_style else "cyan"
        text.append(item.type.value, style=type_style)
        text.append(" ")

        # Format based on type (with optional fade style)
        content_style = extra_style if extra_style else None

        if item.type == ExploredType.SEARCH:
            # Search {query} in {path}
            if item.query:
                text.append(item.query, style=content_style)
            if item.path:
                text.append(" in ", style="dim")
                text.append(item.path, style=content_style)

        elif item.type == ExploredType.READ:
            # Read file1, file2, file3
            if item.names:
                names_str = ", ".join(item.names)
                text.append(names_str, style=content_style)
            elif item.path:
                text.append(item.path, style=content_style)

        elif item.type == ExploredType.LIST:
            # List {path}
            if item.path:
                text.append(item.path, style=content_style)

        return text

    def _build_display(self, tracker: "ExplorationTracker", use_animation: bool = True) -> Group:
        """
        Build the complete display as a Rich Group.

        Args:
            tracker: The ExplorationTracker with items to display
            use_animation: Whether to apply fade-in animation styles

        Returns:
            Rich Group containing all display elements
        """
        elements: List = []

        # Header line
        if tracker.is_active:
            # Use animated spinner for active exploration
            header_table = Table.grid(padding=0)
            header_table.add_column(width=2)  # spinner column
            header_table.add_column()         # text column
            header_table.add_row(
                Spinner("arc", style="yellow"),
                Text("Exploring", style="bold")
            )
            elements.append(header_table)
        else:
            header = Text()
            header.append("• ", style="dim")
            header.append("Explored", style="bold")
            elements.append(header)

        # Get grouped items (consecutive Reads merged)
        grouped_items = tracker.get_grouped_items()

        # Format each item with optional animation style
        for i, item in enumerate(grouped_items):
            extra_style = self._get_item_style(i) if use_animation else ""
            formatted = self._format_item(item, is_first=(i == 0), extra_style=extra_style)
            elements.append(formatted)

        return Group(*elements)

    def render(self, tracker: "ExplorationTracker") -> None:
        """
        Render the exploration display to the console (non-live).

        Args:
            tracker: The ExplorationTracker to render
        """
        if not tracker:
            return

        display = self._build_display(tracker, use_animation=False)
        self.console.print(display)

    def add_item_with_fade(self, tracker: "ExplorationTracker") -> None:
        """
        Add new item and trigger fade-in animation.

        Call this when a new tool starts executing to update the live display
        with a fade-in effect on the new item.

        Args:
            tracker: The ExplorationTracker with the new item
        """
        # Mark the newest item as needing fade-in
        grouped_items = tracker.get_grouped_items()
        if grouped_items:
            new_index = len(grouped_items) - 1
            self._fade_items[new_index] = time.time()

        # Update the live display
        self.update_live(tracker)

    def start_live(self, tracker: "ExplorationTracker") -> None:
        """
        Start live display mode for real-time updates.

        Args:
            tracker: The ExplorationTracker to display
        """
        if self.live:
            self.stop_live()

        self._tracker = tracker
        self._fade_items.clear()
        display = self._build_display(tracker)
        self.live = Live(display, console=self.console, refresh_per_second=4)
        self.live.start()

    def update_live(self, tracker: "ExplorationTracker") -> None:
        """
        Update the live display with current tracker state.

        Args:
            tracker: The ExplorationTracker with updated items
        """
        if not self.live:
            return

        display = self._build_display(tracker)
        self.live.update(display)

    def stop_live(self) -> None:
        """Stop live display mode."""
        if self.live:
            try:
                self.live.stop()
            except Exception:
                pass
            self.live = None
        self._tracker = None
        self._fade_items.clear()

    def render_with_spinner(self, tracker: "ExplorationTracker") -> None:
        """
        Render with a spinner on the header line (for active exploration).

        Args:
            tracker: The ExplorationTracker to render
        """
        if not tracker:
            return

        elements: List = []

        # Header with spinner
        header = Text()
        if tracker.is_active:
            # Use spinner character that will animate
            spinner = Spinner("dots", style="yellow")
            header.append("◦ ", style="yellow")
            header.append("Exploring", style="bold")
        else:
            header.append("• ", style="dim")
            header.append("Explored", style="bold")
        elements.append(header)

        # Items
        grouped_items = tracker.get_grouped_items()
        for i, item in enumerate(grouped_items):
            formatted = self._format_item(item, is_first=(i == 0))
            elements.append(formatted)

        # Print all elements
        for element in elements:
            self.console.print(element)


def render_explored_inline(console: Console, tracker: "ExplorationTracker") -> None:
    """
    Convenience function to render exploration inline.

    Args:
        console: Rich Console instance
        tracker: The ExplorationTracker to render
    """
    display = ExploredDisplay(console)
    display.render(tracker)
