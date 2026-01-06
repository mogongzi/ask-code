"""
Directory listing tool for code exploration.

Provides 'ls' functionality for the LLM to explore project structure.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fnmatch import fnmatch

from .base_tool import BaseTool


class DirectoryTool(BaseTool):
    """List directory contents for codebase exploration."""

    @property
    def name(self) -> str:
        return "list_directory"

    @property
    def description(self) -> str:
        return (
            "List files and directories in a path. "
            "Use to explore project structure before searching or reading files."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory path relative to project root (empty or '.' for root)"
                },
                "recursive": {
                    "type": "boolean",
                    "description": "List recursively (max 2 levels deep)",
                    "default": False
                },
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (e.g., '*.rb', '*.py')",
                    "default": "*"
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Include hidden files/directories (starting with .)",
                    "default": False
                }
            },
            "required": []
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        if not self.validate_input(input_params):
            return {"error": "Invalid input parameters"}

        rel_path = input_params.get("path", "").strip()
        recursive = input_params.get("recursive", False)
        pattern = input_params.get("pattern", "*")
        show_hidden = input_params.get("show_hidden", False)

        # Resolve path relative to project root
        if not self.project_root:
            return {"error": "No project root configured"}

        base_path = Path(self.project_root)
        if rel_path and rel_path != ".":
            target_path = base_path / rel_path
        else:
            target_path = base_path

        # Security: prevent path traversal
        try:
            resolved = target_path.resolve()
            if not str(resolved).startswith(str(base_path.resolve())):
                return {"error": "Path outside project root"}
        except Exception as e:
            return {"error": f"Invalid path: {e}"}

        if not target_path.exists():
            return {"error": f"Path does not exist: {rel_path or '.'}"}

        if not target_path.is_dir():
            return {"error": f"Not a directory: {rel_path}"}

        try:
            entries = self._list_directory(
                target_path,
                base_path,
                pattern,
                show_hidden,
                recursive,
                max_depth=2 if recursive else 0,
                current_depth=0
            )

            return {
                "path": rel_path or ".",
                "total_entries": len(entries),
                "entries": entries
            }

        except PermissionError:
            return {"error": f"Permission denied: {rel_path}"}
        except Exception as e:
            return {"error": f"Failed to list directory: {e}"}

    def _list_directory(
        self,
        path: Path,
        base_path: Path,
        pattern: str,
        show_hidden: bool,
        recursive: bool,
        max_depth: int,
        current_depth: int
    ) -> List[Dict[str, Any]]:
        """List directory contents with optional recursion."""
        entries = []

        try:
            items = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return entries

        for item in items:
            name = item.name

            # Skip hidden files unless requested
            if not show_hidden and name.startswith("."):
                continue

            is_dir = item.is_dir()
            rel_path = str(item.relative_to(base_path))

            # Apply pattern filter to files only
            if not is_dir and not fnmatch(name, pattern):
                continue

            # Use trailing / for directories (like ls -F)
            entry = {"path": rel_path + "/" if is_dir else rel_path}

            entries.append(entry)

            # Recurse into directories if requested
            if is_dir and recursive and current_depth < max_depth:
                children = self._list_directory(
                    item,
                    base_path,
                    pattern,
                    show_hidden,
                    recursive,
                    max_depth,
                    current_depth + 1
                )
                if children:
                    entry["children"] = children

        return entries

    def create_compact_output(self, full_result: Any) -> Any:
        """Create compact output for display."""
        if isinstance(full_result, dict) and "entries" in full_result:
            entries = full_result["entries"]
            # Show just paths in compact mode
            paths = [e["path"] for e in entries[:20]]

            if len(entries) > 20:
                paths.append(f"... and {len(entries) - 20} more")

            return {
                "path": full_result.get("path", "."),
                "total": full_result.get("total_entries", len(entries)),
                "listing": "\n".join(paths)
            }
        return full_result
