"""
ast-grep tool wrapper for the ReAct Rails agent.

Executes `ast-grep` to find structural Ruby patterns. Falls back to a
human-readable result when JSON formatting is not available.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .base_tool import BaseTool


class AstGrepTool(BaseTool):
    @property
    def name(self) -> str:
        return "ast_grep"

    @property
    def description(self) -> str:
        return "Search Ruby code structurally using ast-grep patterns (e.g., class $NAME, def $FN)."

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

        # Build command with correct ast-grep syntax
        cmd = ["ast-grep", "--pattern", pattern] + paths

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
            if r.returncode not in (0, 1):
                return {"error": f"ast-grep error: {r.stderr.strip()}"}

            for line in r.stdout.splitlines():
                if len(matches) >= max_results:
                    break
                # Expected format (human): path:line:col: code
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
                matches.append({
                    "file": rel,
                    "line": line_no,
                    "content": content.strip(),
                    "context": "match",
                })

            return {"matches": matches, "total": len(matches), "pattern": pattern}
        except subprocess.TimeoutExpired:
            return {"error": "ast-grep timed out"}
        except Exception as e:
            return {"error": f"ast-grep failed: {e}"}

    def _rel_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

