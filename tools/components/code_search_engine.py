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

