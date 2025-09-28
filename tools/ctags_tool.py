"""
ctags tool wrapper for the ReAct Rails agent.

Uses `ctags -R -x --languages=ruby` to produce a plain symbol table and filters
by symbol name. Returns file and line for quick jumps.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from .base_tool import BaseTool


class CtagsTool(BaseTool):
    @property
    def name(self) -> str:
        return "ctags"

    @property
    def description(self) -> str:
        return "Query Ruby symbols using universal-ctags output (name, kind, line, file)."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Symbol to find (class/module/method)"},
                "exact": {"type": "boolean", "description": "Exact match (default True)", "default": True},
                "max_results": {"type": "integer", "description": "Limit results", "default": 50},
            },
            "required": ["symbol"],
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        symbol = input_params.get("symbol", "").strip()
        exact = bool(input_params.get("exact", True))
        max_results = int(input_params.get("max_results", 50))

        if not symbol:
            return {"error": "symbol is required"}

        try:
            subprocess.run(["ctags", "--version"], capture_output=True, text=True, timeout=3)
        except Exception:
            return {"error": "ctags not available in PATH"}

        cmd = ["ctags", "-R", "-x", "--languages=ruby", self.project_root]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode not in (0, 1):
                return {"error": f"ctags error: {r.stderr.strip()}"}

            entries: List[Dict[str, Any]] = []
            for line in r.stdout.splitlines():
                # Expected tabular layout: name <space> kind <space> line <space> file ...
                parts = line.split()
                if len(parts) < 4:
                    continue
                name, kind, line_no_str, file_path = parts[:4]
                if exact:
                    ok = name == symbol
                else:
                    ok = symbol in name
                if not ok:
                    continue
                try:
                    line_no = int(line_no_str)
                except ValueError:
                    continue
                entries.append({
                    "name": name,
                    "kind": kind,
                    "line": line_no,
                    "file": self._rel_path(file_path),
                })
                if len(entries) >= max_results:
                    break

            return {"entries": entries, "total": len(entries), "symbol": symbol}
        except subprocess.TimeoutExpired:
            return {"error": "ctags timed out"}
        except Exception as e:
            return {"error": f"ctags failed: {e}"}

    def _rel_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

