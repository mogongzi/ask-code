"""CLI helper to manually run TransactionAnalyzer on a transaction log file."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict

try:
    from tools.transaction_analyzer import TransactionAnalyzer
except ModuleNotFoundError:  # Running as script from within tools/
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    from tools.transaction_analyzer import TransactionAnalyzer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the TransactionAnalyzer tool against a transaction log file."
    )
    parser.add_argument(
        "log_file",
        type=Path,
        help="Path to a SQL transaction log file (MySQL general log style).",
    )
    parser.add_argument(
        "--project-root",
        "-p",
        type=Path,
        default=Path.cwd(),
        help="Path to the Rails project root (defaults to current working directory).",
    )
    parser.add_argument(
        "--max-patterns",
        type=int,
        default=10,
        help="Maximum number of Rails patterns to search when finding source code.",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="Disable searching for source code; only analyze the transaction flow.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable verbose debug logging from the tool.",
    )
    return parser.parse_args()


def build_params(args: argparse.Namespace, log_text: str) -> Dict[str, Any]:
    return {
        "transaction_log": log_text,
        "find_source_code": not args.no_source,
        "max_patterns": args.max_patterns,
    }


def main() -> None:
    args = parse_args()
    project_root = args.project_root.expanduser().resolve()
    log_path = args.log_file.expanduser().resolve()

    if not project_root.exists():
        raise SystemExit(f"Project root not found: {project_root}")

    if not log_path.exists():
        raise SystemExit(f"Log file not found: {log_path}")

    try:
        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:  # pragma: no cover - manual runner
        raise SystemExit(f"Failed to read log file: {exc}") from exc

    tool = TransactionAnalyzer(project_root=str(project_root), debug=args.debug)
    params = build_params(args, log_text)

    try:
        result = tool.execute(params)
    except Exception as exc:  # pragma: no cover - manual runner
        raise SystemExit(f"Tool execution failed: {exc}") from exc

    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
