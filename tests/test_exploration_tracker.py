"""
Tests for the ExplorationTracker module.

Tests cover:
- Basic item addition (search, read, list)
- Consecutive Read grouping logic
- State management (start/stop/clear)
- Edge cases and data integrity
"""

import pytest
import time

from agent.exploration_tracker import (
    ExplorationTracker,
    ExploredItem,
    ExploredType,
)


class TestExploredItem:
    """Tests for ExploredItem dataclass."""

    def test_search_item_creation(self):
        """Test creating a search exploration item."""
        item = ExploredItem(
            type=ExploredType.SEARCH,
            query="SELECT * FROM users",
            path="app/models"
        )
        assert item.type == ExploredType.SEARCH
        assert item.query == "SELECT * FROM users"
        assert item.path == "app/models"
        assert item.names == []
        assert item.timestamp > 0

    def test_read_item_creation(self):
        """Test creating a read exploration item."""
        item = ExploredItem(
            type=ExploredType.READ,
            names=["user.rb", "account.rb"],
            path="app/models"
        )
        assert item.type == ExploredType.READ
        assert item.names == ["user.rb", "account.rb"]
        assert item.path == "app/models"
        assert item.query is None

    def test_list_item_creation(self):
        """Test creating a list exploration item."""
        item = ExploredItem(
            type=ExploredType.LIST,
            path="app/controllers"
        )
        assert item.type == ExploredType.LIST
        assert item.path == "app/controllers"

    def test_names_defaults_to_empty_list(self):
        """Test that names defaults to empty list."""
        item = ExploredItem(type=ExploredType.READ)
        assert item.names == []

    def test_names_none_becomes_empty_list(self):
        """Test that None names becomes empty list via __post_init__."""
        item = ExploredItem(type=ExploredType.READ, names=None)
        assert item.names == []


class TestExplorationTracker:
    """Tests for ExplorationTracker class."""

    def test_initial_state(self):
        """Test initial tracker state."""
        tracker = ExplorationTracker()
        assert len(tracker) == 0
        assert tracker.is_active is False
        assert not tracker  # __bool__ returns False when empty

    def test_add_search(self):
        """Test adding a search operation."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern", "path/to/dir")

        assert len(tracker) == 1
        assert tracker.items[0].type == ExploredType.SEARCH
        assert tracker.items[0].query == "pattern"
        assert tracker.items[0].path == "path/to/dir"

    def test_add_search_default_path(self):
        """Test adding a search with default path."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern")

        assert tracker.items[0].path == "."

    def test_add_read(self):
        """Test adding a read operation."""
        tracker = ExplorationTracker()
        tracker.add_read(["file1.rb", "file2.rb"], "app/models")

        assert len(tracker) == 1
        assert tracker.items[0].type == ExploredType.READ
        assert tracker.items[0].names == ["file1.rb", "file2.rb"]
        assert tracker.items[0].path == "app/models"

    def test_add_read_empty_names(self):
        """Test adding a read with empty names list."""
        tracker = ExplorationTracker()
        tracker.add_read([])

        assert len(tracker) == 1
        assert tracker.items[0].names == []

    def test_add_list(self):
        """Test adding a list operation."""
        tracker = ExplorationTracker()
        tracker.add_list("app/controllers")

        assert len(tracker) == 1
        assert tracker.items[0].type == ExploredType.LIST
        assert tracker.items[0].path == "app/controllers"

    def test_start_stop(self):
        """Test start/stop state management."""
        tracker = ExplorationTracker()

        assert tracker.is_active is False

        tracker.start()
        assert tracker.is_active is True

        tracker.stop()
        assert tracker.is_active is False

    def test_clear(self):
        """Test clearing the tracker."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern1", "path1")
        tracker.add_read(["file.rb"])
        tracker.start()

        assert len(tracker) == 2
        assert tracker.is_active is True

        tracker.clear()

        assert len(tracker) == 0
        assert tracker.is_active is False

    def test_iteration(self):
        """Test iterating over items."""
        tracker = ExplorationTracker()
        tracker.add_search("p1", "path1")
        tracker.add_read(["f1.rb"])
        tracker.add_list("dir1")

        items = list(tracker)
        assert len(items) == 3
        assert items[0].type == ExploredType.SEARCH
        assert items[1].type == ExploredType.READ
        assert items[2].type == ExploredType.LIST

    def test_bool_empty(self):
        """Test __bool__ returns False when empty."""
        tracker = ExplorationTracker()
        assert not tracker

    def test_bool_with_items(self):
        """Test __bool__ returns True when has items."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern", "path")
        assert tracker


class TestExplorationTrackerGrouping:
    """Tests for the get_grouped_items() method - grouping consecutive Reads."""

    def test_no_grouping_single_item(self):
        """Test that single item doesn't change."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern", "path")

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 1
        assert grouped[0].type == ExploredType.SEARCH

    def test_no_grouping_different_types(self):
        """Test that different types are not grouped."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern1", "path1")
        tracker.add_read(["file1.rb"])
        tracker.add_list("dir1")

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 3
        assert grouped[0].type == ExploredType.SEARCH
        assert grouped[1].type == ExploredType.READ
        assert grouped[2].type == ExploredType.LIST

    def test_group_consecutive_reads(self):
        """Test that consecutive Read operations are grouped."""
        tracker = ExplorationTracker()
        tracker.add_read(["file1.rb"])
        tracker.add_read(["file2.rb"])
        tracker.add_read(["file3.rb"])

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 1
        assert grouped[0].type == ExploredType.READ
        assert set(grouped[0].names) == {"file1.rb", "file2.rb", "file3.rb"}

    def test_group_consecutive_reads_preserves_order(self):
        """Test that grouped reads preserve insertion order."""
        tracker = ExplorationTracker()
        tracker.add_read(["a.rb"])
        tracker.add_read(["b.rb"])
        tracker.add_read(["c.rb"])

        grouped = tracker.get_grouped_items()
        assert grouped[0].names == ["a.rb", "b.rb", "c.rb"]

    def test_group_removes_duplicates(self):
        """Test that duplicate filenames are removed."""
        tracker = ExplorationTracker()
        tracker.add_read(["file1.rb"])
        tracker.add_read(["file1.rb"])  # Duplicate
        tracker.add_read(["file2.rb"])

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 1
        assert grouped[0].names == ["file1.rb", "file2.rb"]

    def test_group_mixed_sequence(self):
        """Test grouping in a mixed sequence of operations."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern1", "path1")
        tracker.add_read(["file1.rb"])
        tracker.add_read(["file2.rb"])
        tracker.add_search("pattern2", "path2")
        tracker.add_read(["file3.rb"])
        tracker.add_list("dir1")

        grouped = tracker.get_grouped_items()

        assert len(grouped) == 5
        assert grouped[0].type == ExploredType.SEARCH
        assert grouped[0].query == "pattern1"
        assert grouped[1].type == ExploredType.READ
        assert grouped[1].names == ["file1.rb", "file2.rb"]
        assert grouped[2].type == ExploredType.SEARCH
        assert grouped[2].query == "pattern2"
        assert grouped[3].type == ExploredType.READ
        assert grouped[3].names == ["file3.rb"]
        assert grouped[4].type == ExploredType.LIST

    def test_group_reads_at_start(self):
        """Test grouping when reads are at the start."""
        tracker = ExplorationTracker()
        tracker.add_read(["file1.rb"])
        tracker.add_read(["file2.rb"])
        tracker.add_search("pattern", "path")

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 2
        assert grouped[0].type == ExploredType.READ
        assert grouped[0].names == ["file1.rb", "file2.rb"]
        assert grouped[1].type == ExploredType.SEARCH

    def test_group_reads_at_end(self):
        """Test grouping when reads are at the end."""
        tracker = ExplorationTracker()
        tracker.add_search("pattern", "path")
        tracker.add_read(["file1.rb"])
        tracker.add_read(["file2.rb"])

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 2
        assert grouped[0].type == ExploredType.SEARCH
        assert grouped[1].type == ExploredType.READ
        assert grouped[1].names == ["file1.rb", "file2.rb"]

    def test_empty_tracker_grouping(self):
        """Test grouping on empty tracker."""
        tracker = ExplorationTracker()
        grouped = tracker.get_grouped_items()
        assert grouped == []

    def test_multiple_read_groups(self):
        """Test multiple separate groups of reads."""
        tracker = ExplorationTracker()
        tracker.add_read(["a.rb"])
        tracker.add_read(["b.rb"])
        tracker.add_search("pattern", "path")
        tracker.add_read(["c.rb"])
        tracker.add_read(["d.rb"])

        grouped = tracker.get_grouped_items()
        assert len(grouped) == 3
        assert grouped[0].names == ["a.rb", "b.rb"]
        assert grouped[1].type == ExploredType.SEARCH
        assert grouped[2].names == ["c.rb", "d.rb"]


class TestExploredTypeEnum:
    """Tests for the ExploredType enum."""

    def test_enum_values(self):
        """Test enum value strings."""
        assert ExploredType.READ.value == "Read"
        assert ExploredType.LIST.value == "List"
        assert ExploredType.SEARCH.value == "Search"

    def test_enum_comparison(self):
        """Test enum comparison."""
        assert ExploredType.READ == ExploredType.READ
        assert ExploredType.READ != ExploredType.SEARCH
