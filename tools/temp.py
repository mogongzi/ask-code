"""CLI helper to manually run EnhancedSQLRailsSearch."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch
except ModuleNotFoundError:  # Running as script from within tools/
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from tools.enhanced_sql_rails_search import EnhancedSQLRailsSearch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the EnhancedSQLRailsSearch tool against a Rails project."
    )
    parser.add_argument(
        "sql",
        help="Raw SQL query to trace back to Rails code."
    )
    parser.add_argument(
        "--project-root",
        "-p",
        type=Path,
        default=Path.cwd(),
        help="Path to the Rails project root (defaults to current working directory)."
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=10,
        help="Limit the number of matches returned by the tool."
    )
    parser.add_argument(
        "--skip-usage-sites",
        action="store_true",
        help="Disable lookup of usage sites (definition matches only)."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging from the tool."
    )
    return parser.parse_args()


def build_params(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "sql": args.sql,
        "include_usage_sites": not args.skip_usage_sites,
        "max_results": args.max_results,
    }


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()

    if not project_root.exists():
        raise SystemExit(f"Project root not found: {project_root}")

    tool = EnhancedSQLRailsSearch(project_root=str(project_root), debug=args.debug)
    params = build_params(args)

    try:
        result = tool.execute(params)
    except Exception as exc:  # pragma: no cover - manual runner
        raise SystemExit(f"Tool execution failed: {exc}") from exc

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
