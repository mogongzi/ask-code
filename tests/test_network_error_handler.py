"""Test the NetworkErrorHighlightingHandler."""

import logging
from io import StringIO
from rich.console import Console
from agent.logging import NetworkErrorHighlightingHandler


def test_network_error_handler_highlights():
    """Test that network errors are highlighted by the custom handler."""
    # Create a console that writes to a string buffer
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120)

    # Create logger with custom handler
    logger = logging.getLogger("test_network_error")
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()

    handler = NetworkErrorHighlightingHandler(
        console=console,
        show_time=False,
        show_path=False,
    )
    handler.setFormatter(logging.Formatter(fmt="%(message)s"))
    logger.addHandler(handler)

    # Log a network error
    logger.error("Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke")

    output = buffer.getvalue()

    # Verify the output contains our highlighting
    assert "Network error" in output
    assert "502" in output
    assert "Tip:" in output
    print(f"Output:\n{output}")


def test_regular_error_not_highlighted():
    """Test that regular errors are not highlighted."""
    # Create a console that writes to a string buffer
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120)

    # Create logger with custom handler
    logger = logging.getLogger("test_regular_error")
    logger.setLevel(logging.ERROR)
    logger.handlers.clear()

    handler = NetworkErrorHighlightingHandler(
        console=console,
        show_time=False,
        show_path=False,
    )
    handler.setFormatter(logging.Formatter(fmt="%(message)s"))
    logger.addHandler(handler)

    # Log a regular error
    logger.error("Some other error")

    output = buffer.getvalue()

    # Verify standard formatting (no highlighting tip)
    assert "Some other error" in output
    assert "Tip:" not in output
    print(f"Output:\n{output}")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v", "-s"])
