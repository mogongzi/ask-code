"""
Exploration Tracker for Rails Agent

Tracks tool executions (Search, Read, List) and provides
a Codex-style "Explored" display with grouping and formatting.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Iterator
import time


class ExploredType(Enum):
    """Types of exploration operations."""
    READ = "Read"
    LIST = "List"
    SEARCH = "Search"


@dataclass
class ExploredItem:
    """A single exploration item (search, read, or list operation)."""
    type: ExploredType
    query: Optional[str] = None  # For Search: the pattern
    path: Optional[str] = None   # Directory or file path
    names: List[str] = field(default_factory=list)  # For Read: file names
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        """Ensure names is always a list."""
        if self.names is None:
            self.names = []


@dataclass
class ExplorationTracker:
    """
    Tracks exploration operations during agent execution.

    Provides methods to add operations and retrieve grouped items
    for display (consecutive Read operations are merged).
    """
    items: List[ExploredItem] = field(default_factory=list)
    is_active: bool = False

    def start(self) -> None:
        """Mark exploration as active (for spinner display)."""
        self.is_active = True

    def stop(self) -> None:
        """Mark exploration as complete."""
        self.is_active = False

    def add_search(self, query: str, path: str = ".") -> None:
        """
        Record a search operation.

        Args:
            query: The search pattern/query
            path: The directory or file being searched
        """
        self.items.append(ExploredItem(
            type=ExploredType.SEARCH,
            query=query,
            path=path
        ))

    def add_read(self, file_names: List[str], path: Optional[str] = None) -> None:
        """
        Record a file read operation.

        Args:
            file_names: List of file names that were read
            path: Optional path context
        """
        self.items.append(ExploredItem(
            type=ExploredType.READ,
            names=file_names if file_names else [],
            path=path
        ))

    def add_list(self, path: str) -> None:
        """
        Record a directory listing operation.

        Args:
            path: The directory path or command
        """
        self.items.append(ExploredItem(
            type=ExploredType.LIST,
            path=path
        ))

    def clear(self) -> None:
        """Clear all exploration items and reset state."""
        self.items.clear()
        self.is_active = False

    def get_grouped_items(self) -> List[ExploredItem]:
        """
        Get exploration items with consecutive Reads grouped together.

        Returns:
            List of ExploredItem where consecutive READ items are merged
            into a single item with combined names.
        """
        if not self.items:
            return []

        grouped: List[ExploredItem] = []
        i = 0

        while i < len(self.items):
            current = self.items[i]

            if current.type == ExploredType.READ:
                # Collect consecutive READ operations
                merged_names: List[str] = list(current.names)
                j = i + 1

                while j < len(self.items) and self.items[j].type == ExploredType.READ:
                    merged_names.extend(self.items[j].names)
                    j += 1

                # Remove duplicates while preserving order
                seen = set()
                unique_names = []
                for name in merged_names:
                    if name and name not in seen:
                        seen.add(name)
                        unique_names.append(name)

                # Create merged item
                grouped.append(ExploredItem(
                    type=ExploredType.READ,
                    names=unique_names,
                    path=current.path,
                    timestamp=current.timestamp
                ))
                i = j
            else:
                # Non-READ items are added as-is
                grouped.append(current)
                i += 1

        return grouped

    def __len__(self) -> int:
        """Return number of exploration items."""
        return len(self.items)

    def __iter__(self) -> Iterator[ExploredItem]:
        """Iterate over exploration items."""
        return iter(self.items)

    def __bool__(self) -> bool:
        """Return True if there are any exploration items."""
        return bool(self.items)
