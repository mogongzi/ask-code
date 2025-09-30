"""
Migration analyzer tool for examining Rails database migrations.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base_tool import BaseTool


class MigrationAnalyzer(BaseTool):
    """Tool for analyzing Rails database migrations."""

    @property
    def name(self) -> str:
        return "migration_analyzer"

    @property
    def description(self) -> str:
        return "Analyze Rails database migration files to understand schema changes and database structure."

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Filter migrations for specific table (optional)"
                },
                "migration_type": {
                    "type": "string",
                    "description": "Filter by migration type: 'create_table', 'add_column', 'change_table', or 'all'",
                    "default": "all"
                },
                "limit": {
                    "type": "integer",
                    "description": "Limit number of migrations to analyze (latest first)",
                    "default": 10
                }
            },
            "required": []
        }

    def execute(self, input_params: Dict[str, Any]) -> Any:
        """
        Analyze Rails migration files.

        Args:
            input_params: Migration analysis parameters

        Returns:
            Migration analysis results
        """
        if not self.validate_input(input_params):
            return {"error": "Invalid input parameters"}

        if not self.project_root or not Path(self.project_root).exists():
            return {"error": "Project root not found"}

        table_name = input_params.get("table_name")
        migration_type = input_params.get("migration_type", "all")
        limit = input_params.get("limit", 10)

        # Find migrations directory
        migrations_dir = Path(self.project_root) / "db" / "migrate"
        if not migrations_dir.exists():
            return {"error": f"Migrations directory not found: {migrations_dir}"}

        try:
            # Get migration files (sorted by timestamp, newest first)
            migration_files = sorted(
                migrations_dir.glob("*.rb"),
                key=lambda f: f.name,
                reverse=True
            )[:limit]

            analysis = {
                "migrations": [],
                "table_operations": {},
                "schema_changes": []
            }

            for migration_file in migration_files:
                migration_analysis = self._analyze_migration_file(migration_file, table_name, migration_type)
                if migration_analysis:
                    analysis["migrations"].append(migration_analysis)

            # Summarize table operations
            analysis["table_operations"] = self._summarize_table_operations(analysis["migrations"])

            return analysis

        except Exception as e:
            return {"error": f"Error analyzing migrations: {e}"}

    def _analyze_migration_file(self, migration_file: Path, table_filter: Optional[str],
                               migration_type_filter: str) -> Optional[Dict[str, Any]]:
        """
        Analyze a single migration file.

        Args:
            migration_file: Path to migration file
            table_filter: Filter for specific table
            migration_type_filter: Filter for migration type

        Returns:
            Migration analysis or None if filtered out
        """
        try:
            content = migration_file.read_text(encoding='utf-8')
            lines = content.split('\n')

            migration_info = {
                "file": migration_file.name,
                "relative_path": str(migration_file.relative_to(self.project_root)),
                "timestamp": migration_file.name.split('_')[0],
                "operations": [],
                "tables_affected": set()
            }

            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()

                # Skip comments and empty lines
                if not line_stripped or line_stripped.startswith('#'):
                    continue

                # Extract migration operations
                operation = self._extract_migration_operation(line_stripped, i)
                if operation:
                    migration_info["operations"].append(operation)
                    if operation.get("table"):
                        migration_info["tables_affected"].add(operation["table"])

            # Convert set to list for JSON serialization
            migration_info["tables_affected"] = list(migration_info["tables_affected"])

            # Apply filters
            if table_filter and table_filter not in migration_info["tables_affected"]:
                return None

            if migration_type_filter != "all":
                matching_ops = [op for op in migration_info["operations"]
                              if op.get("type") == migration_type_filter]
                if not matching_ops:
                    return None

            return migration_info

        except Exception as e:
            return {"error": f"Error analyzing {migration_file.name}: {e}"}

    def _extract_migration_operation(self, line: str, line_number: int) -> Optional[Dict[str, Any]]:
        """Extract migration operation from line."""

        # Create table
        create_match = re.search(r'create_table\s+[:\'""](\w+)[\'""]*', line)
        if create_match:
            return {
                "line": line_number,
                "type": "create_table",
                "table": create_match.group(1),
                "content": line
            }

        # Drop table
        drop_match = re.search(r'drop_table\s+[:\'""](\w+)[\'""]*', line)
        if drop_match:
            return {
                "line": line_number,
                "type": "drop_table",
                "table": drop_match.group(1),
                "content": line
            }

        # Add column
        add_column_match = re.search(r'add_column\s+[:\'""](\w+)[\'""]*,\s*[:\'""](\w+)[\'""]*,\s*:(\w+)', line)
        if add_column_match:
            return {
                "line": line_number,
                "type": "add_column",
                "table": add_column_match.group(1),
                "column": add_column_match.group(2),
                "column_type": add_column_match.group(3),
                "content": line
            }

        # Remove column
        remove_column_match = re.search(r'remove_column\s+[:\'""](\w+)[\'""]*,\s*[:\'""](\w+)[\'""]*', line)
        if remove_column_match:
            return {
                "line": line_number,
                "type": "remove_column",
                "table": remove_column_match.group(1),
                "column": remove_column_match.group(2),
                "content": line
            }

        # Add index
        add_index_match = re.search(r'add_index\s+[:\'""](\w+)[\'""]*,\s*[:\'""](\w+)[\'""]*', line)
        if add_index_match:
            return {
                "line": line_number,
                "type": "add_index",
                "table": add_index_match.group(1),
                "column": add_index_match.group(2),
                "content": line
            }

        # Change column
        change_column_match = re.search(r'change_column\s+[:\'""](\w+)[\'""]*,\s*[:\'""](\w+)[\'""]*,\s*:(\w+)', line)
        if change_column_match:
            return {
                "line": line_number,
                "type": "change_column",
                "table": change_column_match.group(1),
                "column": change_column_match.group(2),
                "new_type": change_column_match.group(3),
                "content": line
            }

        return None

    def _summarize_table_operations(self, migrations: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize operations by table."""
        table_ops = {}

        for migration in migrations:
            for operation in migration.get("operations", []):
                table = operation.get("table")
                if table:
                    if table not in table_ops:
                        table_ops[table] = {
                            "create_operations": 0,
                            "modify_operations": 0,
                            "recent_migrations": []
                        }

                    if operation["type"] == "create_table":
                        table_ops[table]["create_operations"] += 1
                    else:
                        table_ops[table]["modify_operations"] += 1

                    table_ops[table]["recent_migrations"].append({
                        "file": migration["file"],
                        "operation": operation["type"],
                        "timestamp": migration["timestamp"]
                    })

        return table_ops

    def validate_input(self, input_params: Dict[str, Any]) -> bool:
        """Validate migration analyzer input parameters."""
        if not super().validate_input(input_params):
            return False

        migration_type = input_params.get("migration_type", "all")
        valid_types = ["all", "create_table", "add_column", "change_table", "drop_table"]
        if migration_type not in valid_types:
            return False

        limit = input_params.get("limit", 10)
        if not isinstance(limit, int) or limit <= 0:
            return False

        return True