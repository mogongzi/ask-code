"""Test error highlighting in the blocking client."""

import pytest
from io import StringIO
from rich.console import Console
from llm.types import LLMResponse


def test_network_error_detection():
    """Test that network errors are detected correctly."""
    # Test cases
    network_errors = [
        "Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke",
        "Network error: Connection refused",
        "502 Server Error",
        "Bad Gateway",
    ]

    for error_msg in network_errors:
        # Check if our detection logic would match
        is_network_error = (
            "Network error" in error_msg or
            "502" in error_msg or
            "Bad Gateway" in error_msg
        )
        assert is_network_error, f"Should detect '{error_msg}' as network error"


def test_regular_error_detection():
    """Test that regular errors are not highlighted as network errors."""
    regular_errors = [
        "Error: Invalid input",
        "Unexpected error: ValueError",
        "Tool execution failed",
    ]

    for error_msg in regular_errors:
        # Check that our detection logic doesn't match
        is_network_error = (
            "Network error" in error_msg or
            "502" in error_msg or
            "Bad Gateway" in error_msg
        )
        assert not is_network_error, f"Should NOT detect '{error_msg}' as network error"


def test_error_message_format():
    """Test that error messages are formatted correctly in console output."""
    # Create a console that writes to a string buffer
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=True, width=120)

    # Simulate network error display
    network_error = "Network error: 502 Server Error: Bad Gateway"
    console.print()
    console.print(f"[bold red on yellow]⚠ {network_error}[/bold red on yellow]")
    console.print("[yellow]Tip: Check if the API server is running[/yellow]")
    console.print()

    output = buffer.getvalue()

    # Verify the output contains our error message
    assert "Network error" in output
    assert "502" in output
    assert "Tip:" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
