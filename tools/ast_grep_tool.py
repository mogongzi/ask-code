"""
ast-grep tool wrapper for the ReAct Rails agent.

Executes `ast-grep` to find structural Ruby patterns using JSON output
for reliable parsing.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .base_tool import BaseTool

# Patterns to exclude from search results (production code only)
_EXCLUDE_PATTERNS = (
    "/test/", "/spec/", "/tests/",
    "_test.rb", "_spec.rb"
)

# Only include Ruby and ERB files
_VALID_EXTENSIONS = (".rb", ".erb")


class AstGrepTool(BaseTool):
    @property
    def name(self) -> str:
        return "ast_grep"

    @property
    def description(self) -> str:
        return "Search Ruby code structurally using ast-grep patterns (e.g., class $NAME, def $FN). Searches .rb and .erb files only, excludes test/spec directories."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "ast-grep pattern, e.g., 'class $NAME'"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Directories or files to search (defaults to project root)",
                },
                "max_results": {"type": "integer", "description": "Limit returned matches", "default": 50},
            },
            "required": ["pattern"],
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        pattern = input_params.get("pattern", "").strip()
        paths = input_params.get("paths") or [self.project_root]
        max_results = int(input_params.get("max_results", 50))

        if not pattern:
            return {"error": "Pattern is required"}

        try:
            # Ensure ast-grep exists
            subprocess.run(["ast-grep", "--version"], capture_output=True, text=True, timeout=3)
        except Exception:
            return {"error": "ast-grep not available in PATH"}

        matches: List[Dict[str, Any]] = []

        # Build command with JSON output for reliable parsing
        cmd = ["ast-grep", "--pattern", pattern, "--json"] + paths

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if r.returncode not in (0, 1):
                return {"error": f"ast-grep error: {r.stderr.strip()}"}

            # Parse JSON output - ast-grep outputs one JSON array
            if r.stdout.strip():
                try:
                    results = json.loads(r.stdout)
                    for item in results:
                        if len(matches) >= max_results:
                            break
                        file_path = item.get("file", "")
                        rel = self._rel_path(file_path)
                        if self._should_exclude(rel):
                            continue  # Skip test files

                        # Get line number from range
                        range_info = item.get("range", {})
                        start = range_info.get("start", {})
                        line_no = start.get("line", 0) + 1  # Convert 0-indexed to 1-indexed

                        # Get the full matched text from 'text' field
                        matched_text = item.get("text", "")

                        # Get surrounding lines for context if available
                        lines = item.get("lines", matched_text)

                        matches.append({
                            "file": rel,
                            "line": line_no,
                            "content": lines.strip() if lines else matched_text.strip()
                        })
                except json.JSONDecodeError:
                    # Fall back to line-by-line parsing if JSON fails
                    return self._parse_human_output(r.stdout, max_results, pattern)

            return {"matches": matches, "total": len(matches), "pattern": pattern}
        except subprocess.TimeoutExpired:
            return {"error": "ast-grep timed out"}
        except Exception as e:
            return {"error": f"ast-grep failed: {e}"}

    def _parse_human_output(self, stdout: str, max_results: int, pattern: str) -> Dict[str, Any]:
        """Fallback parser for human-readable ast-grep output."""
        matches: List[Dict[str, Any]] = []
        for line in stdout.splitlines():
            if len(matches) >= max_results:
                break
            # Expected format (human): path:line:col: code
            # Use rsplit to avoid issues with colons in file content
            parts = line.split(":", 3)
            if len(parts) < 3:
                continue
            file_path = parts[0]
            try:
                line_no = int(parts[1])
            except ValueError:
                continue
            content = parts[3] if len(parts) >= 4 else ""
            rel = self._rel_path(file_path)
            if self._should_exclude(rel):
                continue
            matches.append({
                "file": rel,
                "line": line_no,
                "content": content.strip()
            })
        return {"matches": matches, "total": len(matches), "pattern": pattern}

    def _rel_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

    def _should_exclude(self, file_path: str) -> bool:
        """Check if file should be excluded from results (test directories and non-Ruby files)."""
        # Only include Ruby and ERB files
        if not file_path.endswith(_VALID_EXTENSIONS):
            return True
        # Exclude test directories
        for pattern in _EXCLUDE_PATTERNS:
            if pattern in file_path:
                return True
        return False

