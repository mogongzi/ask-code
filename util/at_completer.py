"""Live @ command autocomplete for file system navigation."""

import os
from pathlib import Path
from typing import List, Iterable, Optional
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class AtCommandCompleter(Completer):
    """Autocompleter for @ commands that provides live file system navigation."""

    def __init__(self, context_manager=None, max_completions: int = 20):
        """Initialize the @ command completer.

        Args:
            context_manager: Optional context manager to show which files are in context
            max_completions: Maximum number of completions to show
        """
        self.context_manager = context_manager
        self.max_completions = max_completions

    def get_completions(self, document: Document, complete_event) -> Iterable[Completion]:
        """Generate completions for @ commands.

        Args:
            document: Current document state from prompt-toolkit
            complete_event: Completion event from prompt-toolkit

        Returns:
            Iterator of Completion objects for file/directory suggestions
        """
        # Get the text before cursor to check for @ commands
        text_before_cursor = document.text_before_cursor

        # Find the last @ character and extract the @ command
        last_at_index = text_before_cursor.rfind('@')
        if last_at_index == -1:
            return

        # Extract the @ command from the last @ to cursor
        at_command = text_before_cursor[last_at_index:]

        # Only complete if this looks like an @ command (starts with @ and no spaces after)
        if not at_command.startswith('@') or ' ' in at_command:
            return

        # Extract the path part after @
        at_path = at_command[1:]  # Remove @ prefix

        try:
            # Generate file/directory completions
            completions = list(self._get_path_completions(at_path))

            # Limit number of completions to avoid overwhelming UI
            for completion in completions[:self.max_completions]:
                yield completion

        except Exception:
            # If anything fails, don't show completions rather than crash
            return

    def _get_path_completions(self, at_path: str) -> List[Completion]:
        """Get file/directory completions for a given @ path.

        Args:
            at_path: Path part after @ symbol

        Returns:
            List of Completion objects
        """
        completions = []

        # Determine the directory to search and partial filename
        if at_path == "":
            # Just @ - complete current directory
            search_dir = os.getcwd()
            partial_name = ""
        elif at_path.endswith("/"):
            # @path/ - complete directory contents
            search_dir = self._resolve_path(at_path)
            partial_name = ""
        else:
            # @path/partial or @partial - complete files starting with partial
            if "/" in at_path:
                # Has directory path
                path_obj = Path(self._resolve_path(at_path))
                search_dir = str(path_obj.parent)
                partial_name = path_obj.name.lower()
            else:
                # No directory path, search current directory
                search_dir = os.getcwd()
                partial_name = at_path.lower()

        # Check if directory exists and is accessible
        if not os.path.exists(search_dir) or not os.path.isdir(search_dir):
            return completions

        try:
            # Get directory entries
            entries = os.listdir(search_dir)

            for entry in sorted(entries):
                entry_path = os.path.join(search_dir, entry)

                # Skip hidden files unless explicitly requested
                if entry.startswith('.') and not at_path.startswith('.'):
                    continue

                # Filter by partial name if provided
                if partial_name and not entry.lower().startswith(partial_name):
                    continue

                # Check if it's a directory or file
                is_dir = os.path.isdir(entry_path)

                # Create completion text
                if "/" in at_path and not at_path.endswith("/"):
                    # Has directory path and partial filename - replace just the partial part
                    dir_part = "/".join(at_path.split("/")[:-1]) + "/"
                    if is_dir:
                        completion_text = f"@{dir_part}{entry}/"
                        display_text = f"{entry}/"
                    else:
                        completion_text = f"@{dir_part}{entry}"
                        display_text = self._format_file_display(entry, entry_path)
                    # Replace from the start of partial filename
                    start_position = -len(at_path.split("/")[-1])
                elif not "/" in at_path and at_path:
                    # No directory, just partial filename in current dir
                    if is_dir:
                        completion_text = f"@{entry}/"
                        display_text = f"{entry}/"
                    else:
                        completion_text = f"@{entry}"
                        display_text = self._format_file_display(entry, entry_path)
                    # Replace the whole @partial
                    start_position = -len(at_path) - 1
                else:
                    # Default case
                    if is_dir:
                        completion_text = f"@{at_path}{entry}/"
                        display_text = f"{entry}/"
                    else:
                        completion_text = f"@{at_path}{entry}"
                        display_text = self._format_file_display(entry, entry_path)
                    # Replace current @... word
                    start_position = -len(at_path) - 1

                completion = Completion(
                    text=completion_text,
                    start_position=start_position,
                    display=display_text
                )

                completions.append(completion)

        except (PermissionError, OSError):
            # Skip directories we can't read
            pass

        return completions

    def _resolve_path(self, at_path: str) -> str:
        """Resolve @ path to absolute filesystem path.

        Args:
            at_path: Path part after @ symbol

        Returns:
            Absolute filesystem path
        """
        if not at_path:
            return os.getcwd()

        # Handle special cases
        if at_path.startswith("~/"):
            return os.path.expanduser(at_path)
        elif at_path.startswith("./"):
            return os.path.abspath(at_path)
        elif os.path.isabs(at_path):
            return at_path
        else:
            # Relative path
            return os.path.join(os.getcwd(), at_path)

    def _format_file_display(self, filename: str, full_path: str) -> str:
        """Format file display text with size and context info.

        Args:
            filename: Base filename
            full_path: Full path to file

        Returns:
            Formatted display string
        """
        try:
            # Get file size
            size = os.path.getsize(full_path)
            size_str = self._format_file_size(size)

            # Check if file is in context
            # Keep display simple: filename and size only
            return f"{filename} ({size_str})"

        except (OSError, PermissionError):
            return f"{filename}"

    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted size string
        """
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}K"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f}M"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f}G"


class FileSystemNavigator:
    """Helper class for navigating file system in @ completions."""

    @staticmethod
    def get_directory_contents(path: str, show_hidden: bool = False) -> List[dict]:
        """Get directory contents with metadata.

        Args:
            path: Directory path to list
            show_hidden: Whether to include hidden files

        Returns:
            List of dictionaries with file/directory metadata
        """
        contents = []

        try:
            if not os.path.exists(path) or not os.path.isdir(path):
                return contents

            entries = os.listdir(path)

            for entry in sorted(entries):
                if entry.startswith('.') and not show_hidden:
                    continue

                entry_path = os.path.join(path, entry)
                is_dir = os.path.isdir(entry_path)

                item = {
                    'name': entry,
                    'path': entry_path,
                    'is_directory': is_dir,
                    'is_hidden': entry.startswith('.'),
                    'readable': os.access(entry_path, os.R_OK)
                }

                if not is_dir and item['readable']:
                    try:
                        item['size'] = os.path.getsize(entry_path)
                    except (OSError, PermissionError):
                        item['size'] = None

                contents.append(item)

        except (PermissionError, OSError):
            pass

        return contents
