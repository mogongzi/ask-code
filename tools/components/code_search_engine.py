from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class CodeSearchEngine:
    """Thin wrapper around ripgrep used by tools to search code.

    Responsibilities:
    - Run ripgrep with consistent flags
    - Normalize paths relative to project_root
    - Filter out test/spec files (production SQL typically not generated there)
    - Provide optional debug logging callback
    """

    def __init__(self, project_root: Optional[str], debug_log: Optional[Callable[[str, Any], None]] = None) -> None:
        self.project_root = project_root
        self.debug_log = debug_log

    def _rel_path(self, file_path: str) -> str:
        try:
            if not self.project_root:
                return file_path
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

    def _is_test_file(self, file_path: str) -> bool:
        # Normalize path separators
        path_lower = file_path.lower().replace('\\', '/')

        # Common test directory patterns
        test_patterns = [
            '/test/',
            '/tests/',
            '/spec/',
            '/specs/',
            '_test.rb',
            '_spec.rb',
            'test_helper.rb',
            'spec_helper.rb'
        ]

        return any(pattern in path_lower for pattern in test_patterns)

    def search(self, pattern: str, file_ext: str) -> List[Dict[str, Any]]:
        """
        Search for pattern in files with given extension.

        Args:
            pattern: Regex pattern to search for
            file_ext: File extension (e.g., 'rb', 'erb')

        Returns:
            List of matches with file, line, and content
        """
        if not self.project_root:
            if self.debug_log:
                self.debug_log("❌ No project root set", None)
            return []

        cmd = [
            "rg", "--line-number", "--with-filename", "-i",
            "--type-add", f"target:*.{file_ext}",
            "--type", "target",
            pattern,
            self.project_root,
        ]

        if self.debug_log:
            self.debug_log("🔍 Executing ripgrep", {
                "pattern": pattern,
                "file_ext": file_ext,
                "command": " ".join(cmd),
            })

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            matches: List[Dict[str, Any]] = []

            if result.returncode in (0, 1):
                for line in result.stdout.splitlines():
                    parts = line.split(":", 2)
                    if len(parts) >= 3:
                        file_path, line_num, content = parts
                        try:
                            rel_path = self._rel_path(file_path)
                            if self._is_test_file(rel_path):
                                continue
                            matches.append({
                                "file": rel_path,
                                "line": int(line_num),
                                "content": content.strip(),
                            })
                        except ValueError:
                            continue

            if self.debug_log:
                self.debug_log("📊 Ripgrep results", {
                    "return_code": result.returncode,
                    "matches_found": len(matches),
                    "stderr": result.stderr[:200] if result.stderr else None,
                })

            return matches
        except Exception as e:
            if self.debug_log:
                self.debug_log("❌ Ripgrep error", f"{type(e).__name__}: {e}")
            return []

    def search_with_context(
        self, pattern: str, file_ext: str, context_lines: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Search for pattern with context lines after the match.

        Useful for finding code blocks like transaction wrappers.

        Args:
            pattern: Regex pattern to search for
            file_ext: File extension (e.g., 'rb')
            context_lines: Number of lines to include after the match

        Returns:
            List of matches with file, line, content, and context_lines
        """
        if not self.project_root:
            if self.debug_log:
                self.debug_log("❌ No project root set", None)
            return []

        cmd = [
            "rg",
            "--line-number",
            "--with-filename",
            "-A", str(context_lines),  # Add context lines after match
            "--type-add", f"target:*.{file_ext}",
            "--type", "target",
            "--glob", "!test/**",  # Exclude test directories
            "--glob", "!spec/**",
            "--glob", "!features/**",
            pattern,
            self.project_root,
        ]

        if self.debug_log:
            self.debug_log("🔍 Executing ripgrep with context", {
                "pattern": pattern,
                "context_lines": context_lines,
            })

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            matches: List[Dict[str, Any]] = []

            if result.returncode in (0, 1):
                current_match = None
                for line in result.stdout.splitlines():
                    if not line.strip():
                        continue

                    # Parse ripgrep output format: "file:line:content" or "file-line-content"
                    import re
                    match = re.match(r'^([^:]+?)([-:])(\\d+)([-:])(.*)$', line)
                    if not match:
                        continue

                    file_path, sep1, line_num, separator, content = match.groups()

                    # New match starts (separator is ':')
                    if separator == ':':
                        if current_match:
                            matches.append(current_match)
                        rel_path = self._rel_path(file_path)
                        if not self._is_test_file(rel_path):
                            current_match = {
                                "file": rel_path,
                                "line": int(line_num),
                                "content": content,
                                "context_lines": []
                            }
                    elif current_match and separator == '-':
                        # Context line (separator is '-')
                        current_match["context_lines"].append(content)

                # Don't forget last match
                if current_match:
                    matches.append(current_match)

            if self.debug_log:
                self.debug_log("📊 Ripgrep context results", {
                    "matches_found": len(matches)
                })

            return matches
        except Exception as e:
            if self.debug_log:
                self.debug_log("❌ Ripgrep context error", f"{type(e).__name__}: {e}")
            return []

    def find_controller_file(self, controller_name: str) -> Optional[Dict[str, str]]:
        """
        Find a Rails controller file by name.

        Args:
            controller_name: Controller name in snake_case (e.g., 'work_pages')

        Returns:
            Dict with 'file' and 'path' keys, or None if not found
        """
        if not self.project_root:
            return None

        controller_file_name = f"{controller_name}_controller.rb"

        cmd = [
            "rg",
            "--files-with-matches",
            "--type", "ruby",
            controller_file_name,
            self.project_root
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0 and result.stdout.strip():
                file_path = result.stdout.strip().split('\n')[0]
                rel_path = self._rel_path(file_path)

                return {
                    "file": rel_path,
                    "path": file_path
                }

        except Exception as e:
            if self.debug_log:
                self.debug_log("❌ Controller file search error", str(e))

        return None

    def find_method_definition(self, file_path: str, method_name: str) -> Optional[int]:
        """
        Find the line number where a method is defined in a file.

        Args:
            file_path: Path to the file (absolute or relative to project_root)
            method_name: Name of the method to find

        Returns:
            Line number where method is defined, or None if not found
        """
        if not self.project_root:
            return None

        # Resolve file path
        full_path = Path(self.project_root) / file_path

        if not full_path.exists():
            return None

        cmd = [
            "rg",
            "-n",
            f"def {method_name}",
            str(full_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                # Parse line number from output (format: "line:content")
                import re
                match = re.match(r'^(\d+):', result.stdout)
                if match:
                    return int(match.group(1))

        except Exception as e:
            if self.debug_log:
                self.debug_log("❌ Method definition search error", str(e))

        return None

    def find_callback_declaration(
        self, model_file: str, callback_type: str, method_name: str
    ) -> Optional[int]:
        """
        Find the line number where a callback is declared in a model file.

        Example: Find "after_save :update_feed" declaration line.

        Args:
            model_file: Path to model file (relative to project_root)
            callback_type: Callback type (e.g., 'after_save', 'after_create')
            method_name: Method name referenced by callback

        Returns:
            Line number of callback declaration, or None if not found
        """
        if not self.project_root:
            return None

        full_path = Path(self.project_root) / model_file

        if not full_path.exists():
            return None

        # Search for callback declaration: after_save :method_name
        cmd = [
            "rg",
            "-n",
            f"{callback_type}.*:{method_name}\\b",
            str(full_path)
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)

            if result.returncode == 0:
                # Parse line number from first match (format: "line:content")
                import re
                match = re.match(r'^(\d+):', result.stdout)
                if match:
                    return int(match.group(1))

        except Exception as e:
            if self.debug_log:
                self.debug_log("❌ Callback declaration search error", str(e))

        return None

    def search_multi_pattern(
        self, initial_pattern: str, filter_patterns: List[str], file_ext: str
    ) -> List[Dict[str, Any]]:
        """
        Search-and-filter: Search for initial pattern, then filter for additional patterns.

        This is a GENERIC search combinator that works for ANY patterns,
        not hardcoded for specific cases.

        Example usage:
        - search_multi_pattern("Member.active", ["offset", "limit"], "rb")
          Finds lines with "Member.active" that also contain "offset" and "limit"

        - search_multi_pattern("500", ["Member", "active"], "rb")
          Finds lines with "500" that also contain "Member" and "active"

        This implements progressive refinement WITHOUT hardcoding patterns.

        Args:
            initial_pattern: First pattern to search for (most distinctive)
            filter_patterns: Additional patterns to filter by (all must be present)
            file_ext: File extension to search in

        Returns:
            List of matches that contain ALL patterns
        """
        # Step 1: Search for initial pattern
        initial_results = self.search(initial_pattern, file_ext)

        if self.debug_log:
            self.debug_log("🔍 Search-and-filter", {
                "initial_pattern": initial_pattern,
                "initial_matches": len(initial_results),
                "filter_patterns": filter_patterns
            })

        # Step 2: Filter results for additional patterns
        filtered_results = []

        for result in initial_results:
            content = result.get("content", "").lower()

            # Check if ALL filter patterns are present
            all_match = all(
                filter_pattern.lower() in content
                for filter_pattern in filter_patterns
            )

            if all_match:
                # Tag with matched patterns for debugging
                result["matched_patterns"] = [initial_pattern] + filter_patterns
                filtered_results.append(result)

        if self.debug_log:
            self.debug_log("✓ Filtered results", {
                "filtered_matches": len(filtered_results)
            })

        return filtered_results

    def search_combined(
        self, patterns: List[str], file_ext: str, match_mode: str = "all"
    ) -> List[Dict[str, Any]]:
        """
        Search for multiple patterns and combine results.

        Args:
            patterns: List of patterns to search for
            file_ext: File extension to search in
            match_mode: "all" (all patterns must match) or "any" (at least one)

        Returns:
            List of matches based on match_mode
        """
        if not patterns:
            return []

        if match_mode == "all":
            # Use search_multi_pattern for AND logic
            return self.search_multi_pattern(patterns[0], patterns[1:], file_ext)

        elif match_mode == "any":
            # OR logic: combine results from all patterns
            all_results = []
            seen = set()

            for pattern in patterns:
                results = self.search(pattern, file_ext)
                for result in results:
                    key = f"{result.get('file', '')}:{result.get('line', 0)}"
                    if key not in seen:
                        seen.add(key)
                        all_results.append(result)

            return all_results

        else:
            raise ValueError(f"Invalid match_mode: {match_mode}. Use 'all' or 'any'.")

