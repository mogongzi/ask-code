"""File context management for LLM conversations."""

import os
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ContextItem:
    """Represents a single file context item."""
    path: str
    content: str
    size: int
    timestamp: datetime

    def __post_init__(self):
        """Validate context item after creation."""
        if not self.content.strip():
            raise ValueError(f"Context file {self.path} is empty or contains only whitespace")


class ContextManager:
    """Manages file context for LLM conversations."""

    def __init__(self, max_total_size: int = 50000, max_files: int = 10):
        """Initialize context manager with size limits.

        Args:
            max_total_size: Maximum total characters across all context files
            max_files: Maximum number of context files allowed
        """
        self.contexts: Dict[str, ContextItem] = {}
        self.max_total_size = max_total_size
        self.max_files = max_files

    def add_file_context(self, file_path: str) -> bool:
        """Add a file to the context.

        Args:
            file_path: Path to the file to add

        Returns:
            True if file was successfully added, False otherwise

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is empty, too large, or limits exceeded
        """
        # Resolve and validate file path
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Check file size limits
        file_size = path.stat().st_size
        if file_size > self.max_total_size:
            raise ValueError(f"File too large: {file_size} bytes (max: {self.max_total_size})")

        # Check total files limit
        if len(self.contexts) >= self.max_files and str(path) not in self.contexts:
            raise ValueError(f"Too many context files (max: {self.max_files})")

        # Read file content
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            raise ValueError(f"File is not valid UTF-8: {file_path}")

        # Check total size after adding this file
        current_size = self.get_total_size()
        new_total_size = current_size + len(content)
        if str(path) not in self.contexts and new_total_size > self.max_total_size:
            raise ValueError(f"Adding file would exceed size limit: {new_total_size} chars (max: {self.max_total_size})")

        # Create context item
        context_item = ContextItem(
            path=str(path),
            content=content,
            size=len(content),
            timestamp=datetime.now()
        )

        # Add to contexts (replacing if already exists)
        self.contexts[str(path)] = context_item
        return True

    def remove_context(self, file_path: str) -> bool:
        """Remove a file from context.

        Args:
            file_path: Path of the file to remove

        Returns:
            True if file was removed, False if not found
        """
        path = str(Path(file_path).resolve())
        if path in self.contexts:
            del self.contexts[path]
            return True
        return False

    def clear_all_context(self) -> None:
        """Remove all context files."""
        self.contexts.clear()

    def list_contexts(self) -> List[Dict[str, str]]:
        """Get list of active context files with metadata.

        Returns:
            List of dictionaries with context file information
        """
        return [
            {
                "path": item.path,
                "size": f"{item.size:,} chars",
                "timestamp": item.timestamp.strftime("%H:%M:%S")
            }
            for item in sorted(self.contexts.values(), key=lambda x: x.timestamp)
        ]

    def get_total_size(self) -> int:
        """Get total size of all context content in characters."""
        return sum(item.size for item in self.contexts.values())

    def get_context_count(self) -> int:
        """Get number of active context files."""
        return len(self.contexts)

    def format_context_for_llm(self) -> str:
        """Format all context files for injection into LLM prompt.

        Returns:
            Formatted context string ready for LLM injection
        """
        if not self.contexts:
            return ""

        # Sort contexts by timestamp (oldest first for consistent ordering)
        sorted_contexts = sorted(self.contexts.values(), key=lambda x: x.timestamp)

        context_parts = []
        context_parts.append("<contextFiles>")

        for item in sorted_contexts:
            # Get relative path for cleaner display
            try:
                rel_path = os.path.relpath(item.path)
                display_path = rel_path if len(rel_path) < len(item.path) else item.path
            except ValueError:
                display_path = item.path

            context_parts.append(f"\n<contextFile name=\"{display_path}\">")
            context_parts.append(item.content)
            context_parts.append("</contextFile>")

        context_parts.append("\n</contextFiles>\n")

        return "\n".join(context_parts)

    def get_status_summary(self) -> str:
        """Get a brief status summary for UI display.

        Returns:
            Short status string like "2 files (1.2k chars)"
        """
        if not self.contexts:
            return "no context"

        file_count = len(self.contexts)
        total_size = self.get_total_size()

        # Format size in a readable way
        if total_size < 1000:
            size_str = f"{total_size}"
        elif total_size < 1000000:
            size_str = f"{total_size/1000:.1f}k"
        else:
            size_str = f"{total_size/1000000:.1f}M"

        file_word = "file" if file_count == 1 else "files"
        return f"{file_count} {file_word} ({size_str} chars)"