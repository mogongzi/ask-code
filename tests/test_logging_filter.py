"""
Test logging configuration filters third-party library logs.

Verifies that verbose mode only shows project logs, not third-party DEBUG logs.
"""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import io
from rich.console import Console

from agent.logging import AgentLogger


def test_verbose_mode_filters_third_party_logs():
    """Test that verbose mode doesn't show third-party library DEBUG logs."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging in verbose mode (DEBUG level)
    AgentLogger.configure(level="DEBUG", console=console)

    # Get loggers
    project_logger = logging.getLogger("agent.test")
    markdown_logger = logging.getLogger("markdown_it")
    asyncio_logger = logging.getLogger("asyncio")

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log at DEBUG level from different sources
    project_logger.debug("This is a project debug log")
    markdown_logger.debug("This is a markdown_it debug log (should be filtered)")
    asyncio_logger.debug("This is an asyncio debug log (should be filtered)")

    # Get output
    output = string_buffer.getvalue()

    # Verify project log appears
    assert "This is a project debug log" in output, "Project DEBUG logs should appear in verbose mode"

    # Verify third-party logs are filtered
    assert "markdown_it" not in output, "markdown_it DEBUG logs should be filtered"
    assert "asyncio debug log" not in output, "asyncio DEBUG logs should be filtered"


def test_non_verbose_mode_filters_project_debug():
    """Test that non-verbose mode doesn't show project DEBUG logs."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging in non-verbose mode (WARNING level)
    AgentLogger.configure(level="WARNING", console=console)

    # Get loggers
    project_logger = logging.getLogger("agent.test")

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log at different levels
    project_logger.debug("This is a project debug log (should be filtered)")
    project_logger.warning("This is a project warning log")

    # Get output
    output = string_buffer.getvalue()

    # Verify DEBUG is filtered, WARNING appears
    assert "debug log" not in output, "Project DEBUG logs should be filtered in non-verbose mode"
    assert "warning log" in output, "Project WARNING logs should appear in non-verbose mode"


def test_third_party_warnings_still_appear():
    """Test that third-party WARNING logs still appear."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging in verbose mode (DEBUG level)
    AgentLogger.configure(level="DEBUG", console=console)

    # Get logger
    markdown_logger = logging.getLogger("markdown_it")

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log at WARNING level
    markdown_logger.warning("This is a markdown_it warning")

    # Get output
    output = string_buffer.getvalue()

    # Verify warning appears
    assert "markdown_it warning" in output, "Third-party WARNING logs should still appear"


if __name__ == "__main__":
    test_verbose_mode_filters_third_party_logs()
    print("✓ Test 1 passed: Verbose mode filters third-party DEBUG logs")

    test_non_verbose_mode_filters_project_debug()
    print("✓ Test 2 passed: Non-verbose mode filters project DEBUG logs")

    test_third_party_warnings_still_appear()
    print("✓ Test 3 passed: Third-party WARNING logs still appear")

    print("\n✅ All logging filter tests passed!")
