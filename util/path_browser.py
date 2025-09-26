"""File and directory browser for @ symbol commands."""

import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class PathItem:
    """Represents a file or directory item."""
    name: str
    path: str
    is_dir: bool
    size: Optional[int] = None
    is_readable: bool = True
    is_hidden: bool = False


class PathBrowser:
    """Handles file system browsing for @ symbol commands."""
    
    def __init__(self, show_hidden: bool = False, max_items: int = 50):
        """Initialize path browser.
        
        Args:
            show_hidden: Whether to show hidden files/directories
            max_items: Maximum number of items to display
        """
        self.show_hidden = show_hidden
        self.max_items = max_items
    
    def parse_at_command(self, command: str) -> Tuple[str, bool]:
        """Parse @ command to extract path and determine if it's a file or directory.
        
        Args:
            command: Command starting with @
            
        Returns:
            Tuple of (resolved_path, is_directory_listing)
        """
        if command == "@":
            # Just @ means current directory
            return os.getcwd(), True
        
        # Remove @ prefix
        path_part = command[1:]
        
        # Handle special cases
        if path_part.startswith("~/"):
            path_part = os.path.expanduser(path_part)
        elif path_part.startswith("./"):
            path_part = os.path.abspath(path_part)
        
        # Resolve path
        try:
            resolved_path = str(Path(path_part).resolve())
        except Exception:
            # If path resolution fails, return as-is
            resolved_path = path_part
        
        # Check if path exists and determine type
        if os.path.exists(resolved_path):
            if os.path.isdir(resolved_path):
                return resolved_path, True
            else:
                return resolved_path, False
        else:
            # Path doesn't exist - could be for directory listing or file addition
            # If it ends with / treat as directory, otherwise as file
            return resolved_path, path_part.endswith("/")
    
    def list_directory(self, directory_path: str) -> List[PathItem]:
        """List contents of a directory.
        
        Args:
            directory_path: Path to directory to list
            
        Returns:
            List of PathItem objects representing directory contents
        """
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")
        
        if not os.path.isdir(directory_path):
            raise ValueError(f"Path is not a directory: {directory_path}")
        
        try:
            items = []
            entries = os.listdir(directory_path)
            
            for entry in sorted(entries):
                entry_path = os.path.join(directory_path, entry)
                
                # Check if hidden
                is_hidden = entry.startswith(".")
                if is_hidden and not self.show_hidden:
                    continue
                
                # Get item info
                try:
                    is_dir = os.path.isdir(entry_path)
                    is_readable = os.access(entry_path, os.R_OK)
                    
                    # Get size for files
                    size = None
                    if not is_dir and is_readable:
                        try:
                            size = os.path.getsize(entry_path)
                        except (OSError, PermissionError):
                            size = None
                    
                    items.append(PathItem(
                        name=entry,
                        path=entry_path,
                        is_dir=is_dir,
                        size=size,
                        is_readable=is_readable,
                        is_hidden=is_hidden
                    ))
                    
                except (OSError, PermissionError):
                    # Skip items we can't access
                    continue
                
                # Limit number of items
                if len(items) >= self.max_items:
                    break
            
            return items
            
        except PermissionError:
            raise ValueError(f"Permission denied accessing directory: {directory_path}")
    
    def format_directory_listing(self, directory_path: str, items: List[PathItem], 
                                context_manager=None, style: str = "icons") -> str:
        """Format directory listing for display.
        
        Args:
            directory_path: Path of the directory being listed
            items: List of PathItem objects to format
            context_manager: Optional context manager to show which files are in context
            style: Display style - "icons" (default) or "terminal"
            
        Returns:
            Formatted string for display
        """
        if not items:
            if style == "terminal":
                return f"{directory_path} (empty)"
            else:
                return f"📁 {directory_path} (empty)"
        
        if style == "terminal":
            return self._format_terminal_style(directory_path, items, context_manager)
        else:
            return self._format_icon_style(directory_path, items, context_manager)
    
    def _format_terminal_style(self, directory_path: str, items: List[PathItem], 
                              context_manager=None) -> str:
        """Format directory listing in terminal-style (like ls command)."""
        lines = []
        
        # Separate directories and files, sort by name
        directories = sorted([item for item in items if item.is_dir], key=lambda x: x.name.lower())
        files = sorted([item for item in items if not item.is_dir], key=lambda x: x.name.lower())
        
        # Add directories first with trailing /
        for item in directories:
            context_mark = ""
            if context_manager and hasattr(context_manager, 'contexts'):
                if item.path in context_manager.contexts:
                    context_mark = " ✓"
            
            if item.is_hidden:
                lines.append(f".{item.name}/{context_mark}")
            else:
                lines.append(f"{item.name}/{context_mark}")
        
        # Add files
        for item in files:
            context_mark = ""
            if context_manager and hasattr(context_manager, 'contexts'):
                if item.path in context_manager.contexts:
                    context_mark = " ✓"
            
            lines.append(f"{item.name}{context_mark}")
        
        # Add usage hint at the end
        lines.append("")
        lines.append("💡 Use @ commands:")
        lines.append("  @filename.txt → add file to context")
        lines.append("  @folder/ → browse folder")
        
        return "\n".join(lines)
    
    def _format_icon_style(self, directory_path: str, items: List[PathItem], 
                          context_manager=None) -> str:
        """Format directory listing with emoji icons (original style)."""
        lines = [f"📁 {directory_path}"]
        
        # Separate directories and files
        directories = [item for item in items if item.is_dir]
        files = [item for item in items if not item.is_dir]
        
        # Add directories first
        for item in directories:
            icon = "📁" if item.is_readable else "🔒"
            hidden_mark = " (hidden)" if item.is_hidden else ""
            lines.append(f"  {icon} {item.name}/{hidden_mark}")
        
        # Add files
        for item in files:
            if not item.is_readable:
                icon = "🔒"
                size_info = ""
            else:
                icon = "📄"
                size_info = f" ({self._format_file_size(item.size)})" if item.size is not None else ""
            
            # Check if file is in context
            context_mark = ""
            if context_manager and hasattr(context_manager, 'contexts'):
                if item.path in context_manager.contexts:
                    context_mark = " ✓"
            
            hidden_mark = " (hidden)" if item.is_hidden else ""
            lines.append(f"  {icon} {item.name}{size_info}{context_mark}{hidden_mark}")
        
        # Add usage hint
        lines.append("")
        lines.append("💡 Use @ commands:")
        lines.append("  @filename.txt → add file to context")
        lines.append("  @folder/ → browse folder")
        
        return "\n".join(lines)
    
    def _format_file_size(self, size_bytes: Optional[int]) -> str:
        """Format file size in human-readable format.
        
        Args:
            size_bytes: Size in bytes
            
        Returns:
            Formatted size string
        """
        if size_bytes is None:
            return "unknown"
        
        if size_bytes < 1024:
            return f"{size_bytes}B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f}K"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f}M"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f}G"
    
    def validate_file_for_context(self, file_path: str) -> Tuple[bool, str]:
        """Validate if a file can be added to context.
        
        Args:
            file_path: Path to file to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        if not os.path.isfile(file_path):
            return False, f"Path is not a file: {file_path}"
        
        if not os.access(file_path, os.R_OK):
            return False, f"File is not readable: {file_path}"
        
        # Check if it's likely a text file
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # Try to read first 1024 bytes
                f.read(1024)
        except UnicodeDecodeError:
            return False, f"File is not valid UTF-8 text: {file_path}"
        except Exception as e:
            return False, f"Error reading file: {e}"
        
        return True, ""
    
    def get_relative_path(self, file_path: str) -> str:
        """Get relative path for display purposes.
        
        Args:
            file_path: Absolute file path
            
        Returns:
            Relative path if shorter, otherwise original path
        """
        try:
            rel_path = os.path.relpath(file_path)
            return rel_path if len(rel_path) < len(file_path) else file_path
        except ValueError:
            # Can happen on Windows with different drives
            return file_path