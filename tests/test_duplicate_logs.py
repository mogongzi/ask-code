"""Test that logs don't appear twice."""

import logging
from io import StringIO
from rich.console import Console
from agent.logging import AgentLogger


def test_no_duplicate_logs():
    """Test that configuring AgentLogger doesn't cause duplicate logs."""
    # Create a console that writes to a string buffer
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120)

    # Configure the logger (this sets up both StructuredLogger and root logger)
    AgentLogger.configure(level="INFO", console=console)

    # Get the logger and log a message
    logger = AgentLogger.get_logger()
    logger.info("Test message")

    output = buffer.getvalue()

    # Count how many times "Test message" appears
    count = output.count("Test message")

    print(f"Output:\n{output}")
    print(f"Message appears {count} time(s)")

    # Should appear exactly once
    assert count == 1, f"Expected message to appear once, but it appeared {count} times"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])
