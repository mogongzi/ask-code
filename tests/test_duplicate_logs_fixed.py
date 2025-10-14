"""
Test that logging doesn't produce duplicate messages.

Verifies that the AgentLogger singleton and module loggers don't cause
duplicate log output when configured multiple times.
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
import io
from rich.console import Console

from agent.logging import AgentLogger


def test_no_duplicate_logs_from_rails_agent_logger():
    """Test that rails_agent logger doesn't log messages twice."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging in verbose mode
    AgentLogger.configure(level="DEBUG", console=console)

    # Get the logger (simulates what ReactRailsAgent does)
    logger = AgentLogger.get_logger()

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log a unique message
    test_message = "ReactRailsAgent initialized test message 12345"
    logger.info(test_message)

    # Get output
    output = string_buffer.getvalue()

    # Count occurrences
    count = output.count(test_message)

    print(f"Output:\n{output}")
    print(f"\nMessage appeared {count} time(s)")

    assert count == 1, f"Message should appear exactly once, but appeared {count} times"


def test_no_duplicate_logs_from_module_loggers():
    """Test that module loggers (agent.*, tools.*, etc.) don't log twice."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging in verbose mode
    AgentLogger.configure(level="DEBUG", console=console)

    # Get module loggers (simulates what other modules do)
    agent_logger = logging.getLogger("agent.test_module")
    tools_logger = logging.getLogger("tools.test_tool")

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log unique messages
    agent_message = "Agent module debug message 67890"
    tools_message = "Tools module debug message ABCDE"

    agent_logger.debug(agent_message)
    tools_logger.debug(tools_message)

    # Get output
    output = string_buffer.getvalue()

    # Count occurrences
    agent_count = output.count(agent_message)
    tools_count = output.count(tools_message)

    print(f"Output:\n{output}")
    print(f"\nAgent message appeared {agent_count} time(s)")
    print(f"Tools message appeared {tools_count} time(s)")

    assert agent_count == 1, f"Agent message should appear exactly once, but appeared {agent_count} times"
    assert tools_count == 1, f"Tools message should appear exactly once, but appeared {tools_count} times"


def test_multiple_configure_calls_dont_duplicate():
    """Test that calling configure() multiple times doesn't cause duplicates."""
    # Create a string buffer to capture log output
    string_buffer = io.StringIO()
    console = Console(file=string_buffer, force_terminal=False)

    # Configure logging multiple times (simulates what might happen in real usage)
    AgentLogger.configure(level="DEBUG", console=console)
    AgentLogger.configure(level="DEBUG", console=console)  # Called again!

    # Get the logger
    logger = AgentLogger.get_logger()

    # Clear buffer
    string_buffer.truncate(0)
    string_buffer.seek(0)

    # Log a message
    test_message = "Multiple configure test message XYZ123"
    logger.info(test_message)

    # Get output
    output = string_buffer.getvalue()

    # Count occurrences
    count = output.count(test_message)

    print(f"Output:\n{output}")
    print(f"\nMessage appeared {count} time(s) after multiple configure() calls")

    assert count == 1, f"Message should appear exactly once even after multiple configure() calls, but appeared {count} times"


if __name__ == "__main__":
    print("=" * 60)
    print("Test 1: rails_agent logger (singleton) doesn't duplicate")
    print("=" * 60)
    test_no_duplicate_logs_from_rails_agent_logger()
    print("\n✓ Test 1 passed\n")

    print("=" * 60)
    print("Test 2: Module loggers (agent.*, tools.*) don't duplicate")
    print("=" * 60)
    test_no_duplicate_logs_from_module_loggers()
    print("\n✓ Test 2 passed\n")

    print("=" * 60)
    print("Test 3: Multiple configure() calls don't cause duplicates")
    print("=" * 60)
    test_multiple_configure_calls_dont_duplicate()
    print("\n✓ Test 3 passed\n")

    print("✅ All duplicate logging tests passed!")
