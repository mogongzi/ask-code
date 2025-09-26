"""
SQL → Rails Code Search Tool

Given a raw SQL query, infer likely Rails/ActiveRecord patterns that would
generate the query and search the project for matching code using ripgrep.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class SQLRailsSearchTool(BaseTool):
    """Infer Rails patterns from SQL and search code for matches."""

    @property
    def name(self) -> str:
        return "sql_rails_search"

    @property
    def description(self) -> str:
        return (
            "Given an SQL query, infer equivalent ActiveRecord/Arel patterns "
            "and search the Rails codebase (rb/erb) for code that likely generates it."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "Raw SQL to search for equivalent code"},
                "file_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File extensions to search",
                    "default": ["rb", "erb"],
                },
                "max_patterns": {
                    "type": "integer",
                    "description": "Max number of inferred patterns to try",
                    "default": 12,
                },
                "max_results_per_pattern": {
                    "type": "integer",
                    "description": "Limit matches per pattern",
                    "default": 20,
                },
                "case_insensitive": {
                    "type": "boolean",
                    "description": "Case-insensitive ripgrep search",
                    "default": True,
                },
            },
            "required": ["sql"],
        }

    async def execute(self, input_params: Dict[str, Any]) -> Any:
        if not self.validate_input(input_params):
            return {"error": "Invalid input"}

        sql = input_params.get("sql", "").strip()
        if not sql:
            return {"error": "Empty SQL"}

        # Check if this is a transaction log (multiple queries with timestamps)
        if self._is_transaction_log(sql):
            return {
                "error": "This appears to be a complete transaction log. Use the transaction_analyzer tool instead.",
                "suggestion": "Try using the transaction_analyzer tool to analyze the entire transaction flow.",
                "detected_queries": self._count_queries_in_log(sql)
            }

        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        file_types = input_params.get("file_types", ["rb", "erb"]) or ["rb", "erb"]
        max_patterns = int(input_params.get("max_patterns", 12))
        max_per = int(input_params.get("max_results_per_pattern", 20))
        case_insensitive = bool(input_params.get("case_insensitive", True))

        # Quick preflight: is ripgrep available?
        try:
            subprocess.run(["rg", "--version"], capture_output=True, text=True, timeout=3)
        except Exception:
            return {"error": "ripgrep (rg) not available in PATH"}

        parsed = self._parse_sql(sql)
        patterns = self._infer_patterns(parsed)

        # Cap number of patterns to avoid long searches
        patterns = patterns[:max_patterns]

        # Execute rg for each pattern and collect results
        results: List[Dict[str, Any]] = []
        pattern_summaries: List[Dict[str, Any]] = []
        seen_keys = set()

        for pat in patterns:
            rg_cmd = ["rg", "--line-number", "--with-filename"]
            if case_insensitive:
                rg_cmd.append("-i")

            # Restrict by file types
            for ext in file_types:
                rg_cmd.extend(["--type-add", f"target:{ext}", "--type", "target"])

            # Use -S (smart case, literal/regex consistent) and -n -H already set
            rg_cmd.extend([pat["regex"], self.project_root])

            try:
                r = subprocess.run(rg_cmd, capture_output=True, text=True, timeout=10)
            except subprocess.TimeoutExpired:
                pattern_summaries.append({"pattern": pat["label"], "regex": pat["regex"], "matches": 0, "error": "timeout"})
                continue
            except Exception as e:
                pattern_summaries.append({"pattern": pat["label"], "regex": pat["regex"], "matches": 0, "error": str(e)})
                continue

            count = 0
            if r.returncode in (0, 1):  # 0=matches, 1=no matches
                lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
                for ln in lines:
                    if count >= max_per:
                        break
                    parts = ln.split(":", 2)
                    if len(parts) < 3:
                        continue
                    file_path, line_str, content = parts
                    try:
                        line_no = int(line_str)
                    except ValueError:
                        continue

                    # Make de-duplication key
                    rel_path = self._rel_path(file_path)
                    key = (rel_path, line_no, content.strip())
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)

                    results.append(
                        {
                            "file": rel_path,
                            "line": line_no,
                            "content": content.strip(),
                            "matched_pattern": pat["label"],
                        }
                    )
                    count += 1

            pattern_summaries.append({"pattern": pat["label"], "regex": pat["regex"], "matches": count})

        return {
            "sql": sql,
            "tables": parsed.get("tables", []),
            "columns": parsed.get("columns", []),
            "models": parsed.get("models", []),
            "patterns_tried": pattern_summaries,
            "results": results,
            "total_results": len(results),
        }

    def _rel_path(self, file_path: str) -> str:
        try:
            return str(Path(file_path).resolve().relative_to(Path(self.project_root).resolve()))
        except Exception:
            return file_path

    def _parse_sql(self, sql: str) -> Dict[str, Any]:
        s = sql.strip()
        s_up = s.upper()

        # Extract table after FROM (handles quoted/backticked and schema-qualified)
        table = None
        m_from = re.search(r"\bFROM\s+([\w\.`\"]+)", s_up, re.IGNORECASE)
        if m_from:
            raw = m_from.group(1)
            table = raw.replace("`", "").replace("\"", "").split(".")[-1]

        # Extract simple WHERE expression for a single column comparison
        where_cols: List[str] = []
        m_where = re.search(r"\bWHERE\s+(.+?)(?:\bORDER\b|\bGROUP\b|\bLIMIT\b|$)", s, flags=re.IGNORECASE)
        if m_where:
            where = m_where.group(1)
            # Very light column token extraction (matches words before operators)
            for col in re.findall(r"([a-zA-Z_][\w\.]*)\s*(?:=|>=|<=|<>|!=|>|<)", where):
                where_cols.append(col.split(".")[-1])

        tables = [table] if table else []
        models = [self._table_to_model(t) for t in tables if t]

        return {
            "tables": tables,
            "columns": list(dict.fromkeys(where_cols)),  # unique preserve order
            "models": models,
        }

    def _table_to_model(self, table: str) -> str:
        # Minimal singularize + CamelCase (good enough for common cases)
        t = table.lower()
        if t.endswith("ies"):
            singular = t[:-3] + "y"
        elif t.endswith("ses"):
            singular = t[:-2]
        elif t.endswith("es") and not t.endswith("ses"):
            singular = t[:-2]
        elif t.endswith("s"):
            singular = t[:-1]
        else:
            singular = t

        return "".join(part.capitalize() for part in singular.split("_"))

    def _infer_patterns(self, parsed: Dict[str, Any]) -> List[Dict[str, str]]:
        """Build a prioritized list of ripgrep regex patterns to try."""
        tables = parsed.get("tables", [])
        cols = parsed.get("columns", [])
        models = parsed.get("models", [])

        patterns: List[Dict[str, str]] = []

        # 1) Literal SQL appearance (exact-ish)
        if tables:
            tbl = re.escape(tables[0])
            patterns.append({
                "label": f"literal SQL for {tables[0]}",
                "regex": rf"SELECT\s+.*FROM\s+{tbl}.*WHERE",
            })

        # 2) Model.where with column in string
        for model in models:
            for col in cols or ["id", "price", "name"]:
                col_re = re.escape(col)
                patterns.append({
                    "label": f"{model}.where string with {col}",
                    "regex": rf"{re.escape(model)}\.where\([^\)]*\b{col_re}\b[^\)]*\)",
                })

        # 3) Generic where with column in string (scopes, relations)
        for col in cols or ["id", "price", "name"]:
            col_re = re.escape(col)
            patterns.append({
                "label": f"where string with {col}",
                "regex": rf"\.where\([^\)]*\b{col_re}\b[^\)]*\)",
            })

        # 4) Parameterized where("col > ?", value)
        for col in cols:
            col_re = re.escape(col)
            patterns.append({
                "label": f"parameterized where on {col}",
                "regex": rf"\.where\(\s*['\"]\s*[^'\"]*\b{col_re}\b\s*[<>!=]=?\s*\?",
            })

        # 5) Table-qualified where("table.col ...")
        if tables:
            t = re.escape(tables[0])
            for col in cols or ["id", "price", "name"]:
                col_re = re.escape(col)
                patterns.append({
                    "label": f"qualified where {tables[0]}.{col}",
                    "regex": rf"\.where\([^\)]*\b{t}\s*\.\s*{col_re}\b[^\)]*\)",
                })

        # 6) Arel: Model.arel_table[:col].op(value)
        for model in models:
            for col in cols or ["id", "price", "name"]:
                col_re = re.escape(col)
                patterns.append({
                    "label": f"Arel {model}[:{col}] comparison",
                    "regex": rf"{re.escape(model)}\.arel_table\s*\[:{col_re}\]\s*\.(?:gt|gteq|lt|lteq|eq|not_eq)\s*\(",
                })

        # 7) Named scopes referencing column
        for col in cols or ["id", "price", "name"]:
            col_re = re.escape(col)
            patterns.append({
                "label": f"scope with {col}",
                # Use doubled braces in f-string to emit literal '{' and '}' while keeping backslashes
                "regex": rf"scope\s*:\w+\s*,\s*->\s*\{{[^\}}]*where\([^\)]*\b{col_re}\b[^\)]*\)\s*\}}",
            })

        # 8) Joins to table then where on column
        if tables:
            t = re.escape(tables[0])
            for col in cols or ["id", "price", "name"]:
                col_re = re.escape(col)
                patterns.append({
                    "label": f"joins(:{tables[0]}) then where {col}",
                    "regex": rf"\.joins\([^\)]*:{t}[^\)]*\)[^\n]*?\.where\([^\)]*\b{col_re}\b",
                })

        # 9) find_by/find_by_ with conditions
        for model in models:
            for col in cols or ["id", "price", "name"]:
                col_re = re.escape(col)
                patterns.append({
                    "label": f"{model}.find_by {col}",
                    "regex": rf"{re.escape(model)}\.(?:find_by|find_by_\w+)\([^\)]*\b{col_re}\b",
                })

        # 10) Raw SQL via find_by_sql
        for model in models:
            patterns.append({
                "label": f"{model}.find_by_sql",
                "regex": rf"{re.escape(model)}\.find_by_sql\(",
            })

        # 11) sanitize_sql with where
        patterns.append({
            "label": "sanitize_sql in where",
            "regex": r"\.where\([^\)]*sanitize_sql\([^\)]*\)\)",
        })

        return patterns

    def _is_transaction_log(self, sql: str) -> bool:
        """Check if the input appears to be a transaction log with multiple queries."""
        lines = sql.strip().split('\n')

        # Look for timestamp patterns typical of MySQL general log
        timestamp_pattern = r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s+\d+\s+\w+'

        # Count lines that look like log entries
        log_lines = sum(1 for line in lines if re.match(timestamp_pattern, line.strip()))

        # If we have multiple timestamped entries, it's likely a transaction log
        if log_lines >= 3:
            return True

        # Also check for explicit transaction boundaries
        has_begin = any('BEGIN' in line.upper() for line in lines)
        has_commit = any('COMMIT' in line.upper() for line in lines)
        multiple_queries = len([line for line in lines if any(op in line.upper() for op in ['SELECT', 'INSERT', 'UPDATE', 'DELETE'])]) >= 3

        return has_begin and has_commit and multiple_queries

    def _count_queries_in_log(self, sql: str) -> int:
        """Count the number of SQL queries in a transaction log."""
        lines = sql.strip().split('\n')
        query_count = 0

        for line in lines:
            line_clean = line.strip()
            # Skip empty lines
            if not line_clean:
                continue

            # Look for SQL operations anywhere in the line (after timestamp)
            line_upper = line_clean.upper()
            if any(op in line_upper for op in ['SELECT', 'INSERT', 'UPDATE', 'DELETE', 'BEGIN', 'COMMIT']):
                query_count += 1

        return query_count
