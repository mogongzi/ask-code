#!/usr/bin/env python3
"""
Test runner script for ride_rails components.
"""
import sys
import subprocess
import os
from pathlib import Path

def run_tests(test_pattern=None, verbose=False, coverage=False):
    """
    Run tests with pytest.

    Args:
        test_pattern: Specific test pattern to run (e.g., "test_agent_config")
        verbose: Enable verbose output
        coverage: Enable coverage reporting
    """
    # Ensure we're in the right directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Build pytest command
    cmd = ["python", "-m", "pytest"]

    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-q")

    if coverage:
        cmd.extend([
            "--cov=agent",
            "--cov=tools",
            "--cov-report=term-missing",
            "--cov-report=html:tests/coverage_html"
        ])

    # Add test directory
    if test_pattern:
        cmd.append(f"tests/{test_pattern}")
    else:
        cmd.append("tests/")

    # Add additional pytest options
    cmd.extend([
        "--tb=short",  # Shorter traceback format
        "-x",          # Stop on first failure
    ])

    print(f"Running: {' '.join(cmd)}")
    print("-" * 60)

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        return 1

def main():
    """Main test runner entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Run ride_rails tests")
    parser.add_argument(
        "pattern",
        nargs="?",
        help="Test pattern to run (e.g., test_agent_config.py)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    parser.add_argument(
        "-c", "--coverage",
        action="store_true",
        help="Enable coverage reporting"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available test files"
    )

    args = parser.parse_args()

    if args.list:
        print("Available test files:")
        test_dir = Path(__file__).parent
        for test_file in sorted(test_dir.glob("test_*.py")):
            print(f"  {test_file.name}")
        return 0

    return run_tests(
        test_pattern=args.pattern,
        verbose=args.verbose,
        coverage=args.coverage
    )

if __name__ == "__main__":
    sys.exit(main())