"""
File reader tool for reading source files within the Rails project.

This tool allows the agent to read specific files or line ranges,
providing detailed code context after search operations.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .base_tool import BaseTool


class FileReaderTool(BaseTool):
    """Tool for reading source files within the project."""

    # Maximum lines to read at once to prevent token overflow
    MAX_LINES = 500

    @property
    def name(self) -> str:
        return "file_reader"

    @property
    def description(self) -> str:
        return (
            "Read source files from the Rails project. "
            "Use this after search tools to examine specific files or code sections. "
            "Can read entire files or specific line ranges."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file relative to project root (e.g., 'app/models/user.rb')"
                },
                "line_start": {
                    "type": "integer",
                    "description": "Starting line number (1-indexed, optional). If omitted, reads from beginning.",
                    "minimum": 1
                },
                "line_end": {
                    "type": "integer",
                    "description": "Ending line number (inclusive, optional). If omitted, reads to end or max lines.",
                    "minimum": 1
                }
            },
            "required": ["file_path"]
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Read a file from the project.

        Args:
            input_params: File reading parameters

        Returns:
            File contents with line numbers or error message
        """
        self._debug_input(input_params)

        if not self.validate_input(input_params):
            error_result = {"error": "Invalid input parameters"}
            self._debug_output(error_result)
            return error_result

        if not self.project_root or not Path(self.project_root).exists():
            error_result = {"error": "Project root not found"}
            self._debug_output(error_result)
            return error_result

        file_path = input_params.get("file_path", "")
        line_start = input_params.get("line_start")
        line_end = input_params.get("line_end")

        self._debug_log("📖 Reading file", {
            "file_path": file_path,
            "line_start": line_start,
            "line_end": line_end
        })

        # Resolve and validate file path
        try:
            full_path = self._resolve_file_path(file_path)
        except ValueError as e:
            error_result = {"error": str(e)}
            self._debug_output(error_result)
            return error_result

        # Read file contents
        try:
            result = self._read_file_content(full_path, line_start, line_end)
            self._debug_output(result)
            return result
        except Exception as e:
            error_result = {"error": f"Error reading file: {e}"}
            self._debug_output(error_result)
            return error_result

    def _resolve_file_path(self, file_path: str) -> Path:
        """
        Resolve and validate file path.

        Args:
            file_path: Relative file path

        Returns:
            Resolved absolute path

        Raises:
            ValueError: If path is invalid or outside project root
        """
        # Normalize path separators
        file_path = file_path.replace('\\', '/')

        # Construct full path
        project_path = Path(self.project_root)
        full_path = project_path / file_path

        # Resolve both paths - this handles symlinks like /var -> /private/var on macOS
        try:
            project_resolved = project_path.resolve()
            full_resolved = full_path.resolve()
        except (OSError, RuntimeError):
            raise ValueError(f"Cannot resolve path: {file_path}")

        # Security: Ensure file is within project root (compare resolved paths)
        try:
            full_resolved.relative_to(project_resolved)
        except ValueError:
            raise ValueError(f"File path '{file_path}' is outside project root")

        # Check file exists
        if not full_resolved.exists():
            raise ValueError(f"File not found: {file_path}")

        # Check it's a file, not directory
        if not full_resolved.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        return full_resolved

    def _read_file_content(
        self,
        file_path: Path,
        line_start: Optional[int],
        line_end: Optional[int]
    ) -> Dict[str, Any]:
        """
        Read file contents with optional line range.

        Args:
            file_path: Absolute file path
            line_start: Starting line (1-indexed, optional)
            line_end: Ending line (inclusive, optional)

        Returns:
            Dictionary with file contents and metadata
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                all_lines = f.readlines()
        except UnicodeDecodeError:
            # Try with latin-1 fallback
            with open(file_path, 'r', encoding='latin-1') as f:
                all_lines = f.readlines()

        total_lines = len(all_lines)

        # Determine line range
        if line_start is None:
            start_idx = 0
        else:
            start_idx = max(0, line_start - 1)  # Convert to 0-indexed

        if line_end is None:
            end_idx = min(total_lines, start_idx + self.MAX_LINES)
        else:
            end_idx = min(total_lines, line_end)  # Already 0-indexed for slicing

        # Validate range
        if start_idx >= total_lines:
            return {
                "error": f"Starting line {line_start} exceeds file length ({total_lines} lines)"
            }

        if line_start and line_end and line_end < line_start:
            return {
                "error": f"Invalid range: line_end ({line_end}) < line_start ({line_start})"
            }

        # Extract lines
        selected_lines = all_lines[start_idx:end_idx]
        actual_end = start_idx + len(selected_lines)

        # Check if truncated
        truncated = False
        if line_end is None and actual_end < total_lines:
            truncated = True

        # Format with line numbers
        numbered_lines = []
        for i, line in enumerate(selected_lines, start=start_idx + 1):
            numbered_lines.append(f"{i:5d} | {line.rstrip()}")

        result = {
            "file_path": str(file_path.relative_to(Path(self.project_root).resolve())),
            "total_lines": total_lines,
            "lines_shown": len(selected_lines),
            "line_range": [start_idx + 1, actual_end],
            "content": "\n".join(numbered_lines),
            "truncated": truncated
        }

        if truncated:
            result["message"] = f"Showing first {self.MAX_LINES} lines. Use line_start/line_end for specific range."

        return result

    def format_result(self, result: Any) -> str:
        """Format file reading result for LLM consumption."""
        if isinstance(result, str):
            return result  # Error message

        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}"

        if not isinstance(result, dict):
            return str(result)

        # Build formatted output
        lines = []
        lines.append(f"## File: {result['file_path']}")
        lines.append(f"**Total lines**: {result['total_lines']}")
        lines.append(f"**Showing**: Lines {result['line_range'][0]}-{result['line_range'][1]} ({result['lines_shown']} lines)")

        if result.get("truncated"):
            lines.append(f"⚠️ {result['message']}")

        lines.append("\n```ruby")
        lines.append(result['content'])
        lines.append("```")

        return "\n".join(lines)

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate file reader input parameters."""
        if not super().validate_input(input_params):
            return False

        file_path = input_params.get("file_path")
        if not file_path or not isinstance(file_path, str):
            return False

        # Validate line numbers if provided
        line_start = input_params.get("line_start")
        if line_start is not None:
            if not isinstance(line_start, int) or line_start < 1:
                return False

        line_end = input_params.get("line_end")
        if line_end is not None:
            if not isinstance(line_end, int) or line_end < 1:
                return False

        return True