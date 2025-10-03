#!/usr/bin/env python3
"""
Test script for BlockingClient spinner animation.

This script simulates a slow API response to verify that the spinner
animation works correctly in blocking mode.
"""
import sys
import os
# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from unittest.mock import Mock, patch
from llm.clients import BlockingClient
from llm.types import Provider
from rich.console import Console

def test_spinner_animation():
    """Test that the spinner shows during a simulated slow API call."""
    console = Console()
    client = BlockingClient(console=console, provider=Provider.BEDROCK)

    # Mock response data
    mock_response_data = {
        "content": [
            {"type": "text", "text": "This is a test response"}
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        },
        "model": "claude-sonnet-3-5"
    }

    console.print("[bold]Testing BlockingClient spinner animation...[/bold]\n")

    # Simulate a slow API response (3 seconds)
    def slow_post(*args, **kwargs):
        console.print("[dim]Simulating 3-second API delay...[/dim]")
        time.sleep(3)

        # Create mock response object
        mock_resp = Mock()
        mock_resp.json.return_value = mock_response_data
        mock_resp.raise_for_status = Mock()
        return mock_resp

    # Test with mock
    with patch('requests.post', side_effect=slow_post):
        result = client.send_message(
            url="http://localhost:8000/invoke",
            payload={"messages": [{"role": "user", "content": "test"}]}
        )

    console.print("\n[bold green]✓ Spinner test completed![/bold green]")
    console.print(f"Response text: {result.text}")
    console.print(f"Tokens: {result.tokens}")
    console.print(f"Model: {result.model_name}")

if __name__ == "__main__":
    test_spinner_animation()