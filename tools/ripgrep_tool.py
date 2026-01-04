"""
Ripgrep tool for fast text search in Rails projects.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class RipgrepTool(BaseTool):
    """Tool for fast text search using ripgrep."""

    @property
    def name(self) -> str:
        return "ripgrep"

    @property
    def description(self) -> str:
        return "Fast text search in Rails codebase using ripgrep. Searches production code only (excludes test/ spec/ directories). Excellent for finding exact code patterns, method calls, and string matches."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for"
                },
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to search (e.g., ['rb', 'erb'])",
                    "default": ["rb"]
                },
                "context": {
                    "type": "integer",
                    "description": "Number of context lines to show around matches",
                    "default": 2
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 20
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Perform case-insensitive search",
                    "default": True
                }
            },
            "required": ["pattern"]
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Execute ripgrep search.

        Args:
            input_params: Search parameters

        Returns:
            Search results with file paths, line numbers, and content
        """
        # Note: _debug_input/_debug_output are handled by execute_with_debug() wrapper
        # Only use _debug_log() for intermediate steps here

        # Check for specific validation errors to provide better messages
        pattern = input_params.get("pattern", "")
        if not pattern:
            return {"error": "Pattern is required"}

        if not self.validate_input(input_params):
            return {"error": "Invalid input parameters"}

        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        file_types = input_params.get("file_types", ["rb"])
        context = input_params.get("context", 2)
        max_results = input_params.get("max_results", 20)
        case_insensitive = bool(input_params.get("case_insensitive", True))

        self._debug_log("🔍 Search parameters", {
            "pattern": pattern,
            "file_types": file_types,
            "context": context,
            "max_results": max_results,
            "case_insensitive": case_insensitive
        })

        try:
            # Build ripgrep command
            cmd = ["rg", "--line-number", "--with-filename"]

            # Case-insensitive by default to avoid false negatives on Rails conventions
            if case_insensitive:
                cmd.append("-i")

            # Add context if specified
            if context > 0:
                cmd.extend(["-C", str(context)])

            # Exclude test directories by default (production code search)
            # Use **/ prefix to match test directories at any depth in the tree
            cmd.extend([
                "--glob", "!**/test/**",
                "--glob", "!**/spec/**",
                "--glob", "!**/tests/**",
                "--glob", "!**/*_test.rb",
                "--glob", "!**/*_spec.rb"
            ])

            # Add file type filters
            for file_type in file_types:
                cmd.extend(["--type-add", f"target:*.{file_type}", "--type", "target"])

            # Add pattern and search path
            cmd.extend([pattern, self.project_root])

            self._debug_log("🚀 Executing ripgrep command", " ".join(cmd))

            # Execute ripgrep
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10
            )

            self._debug_log("📊 Ripgrep execution", {
                "return_code": result.returncode,
                "stderr": result.stderr[:200] if result.stderr else None,
                "stdout_lines": len(result.stdout.splitlines()) if result.stdout else 0
            })

            if result.returncode != 0:
                if result.returncode == 1:  # No matches found
                    return {"matches": [], "total": 0, "message": "No matches found"}
                else:
                    return {"error": f"Ripgrep error: {result.stderr}"}

            # Parse results
            matches = self._parse_ripgrep_output(result.stdout, max_results)

            return {
                "matches": matches,
                "total": len(matches),
                "pattern": pattern,
                "file_types": file_types,
                "case_insensitive": case_insensitive
            }

        except subprocess.TimeoutExpired:
            return {"error": "Search timed out"}
        except Exception as e:
            return {"error": f"Error executing ripgrep: {e}"}

    def create_compact_output(self, full_result: Dict[str, Any]) -> Dict[str, Any]:
        """Create a compact summary for non-verbose mode."""
        if "error" in full_result or "message" in full_result:
            return full_result

        matches = full_result.get("matches", [])
        total = len(matches)
        pattern = full_result.get("pattern", "")

        # Show top 5 matches
        top_matches = []
        for match in matches[:5]:
            snippet = match.get("content", "")
            if len(snippet) > 80:
                snippet = snippet[:77] + "..."
            top_matches.append({
                "file": match.get("file", ""),
                "line": match.get("line", 0),
                "context": match.get("context", "match"),
                "snippet": snippet
            })

        compact = {
            "summary": f"Found {total} match{'es' if total != 1 else ''} for pattern: {pattern}",
            "top_matches": top_matches
        }

        if total > 5:
            compact["hint"] = f"Showing top 5 of {total} matches. Use --verbose to see all."

        return compact

    def _parse_ripgrep_output(self, output: str, max_results: int) -> List[Dict[str, Any]]:
        """
        Parse ripgrep output into structured results.

        Args:
            output: Raw ripgrep output
            max_results: Maximum number of results to return

        Returns:
            List of match dictionaries
        """
        matches = []
        lines = output.strip().split('\n')

        for line in lines:
            if not line.strip():
                continue

            # Stop if we've reached max results
            if len(matches) >= max_results:
                break

            # Parse ripgrep output format: file:line:content
            if ':' in line:
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    file_path = parts[0]
                    try:
                        line_number = int(parts[1])
                        content = parts[2]

                        # Make path relative to project root
                        try:
                            rel_path = Path(file_path).relative_to(self.project_root)
                        except ValueError:
                            rel_path = Path(file_path)

                        matches.append({
                            "file": str(rel_path),
                            "line": line_number,
                            "content": content.strip(),
                            "context": "match"
                        })
                    except ValueError:
                        # Line number parsing failed, might be context line
                        continue

        return matches

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate ripgrep input parameters."""
        if not super().validate_input(input_params):
            return False

        pattern = input_params.get("pattern")
        if not pattern or not isinstance(pattern, str):
            return False

        file_types = input_params.get("file_types", ["rb"])
        if not isinstance(file_types, list):
            return False

        return True
