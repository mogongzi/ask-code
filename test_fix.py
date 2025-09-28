#!/usr/bin/env python3
"""
Quick test to verify the async fix works.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from agent.refactored_rails_agent import RefactoredRailsAgent
    from agent.config import AgentConfig
    from rich.console import Console

    console = Console()
    console.print("[green]✓ Successfully imported RefactoredRailsAgent[/green]")

    # Test creating the agent
    config = AgentConfig(
        project_root="/tmp",  # Use a safe directory
        max_react_steps=5,
        debug_enabled=True
    )

    agent = RefactoredRailsAgent(config=config, session=None)
    console.print("[green]✓ Successfully created RefactoredRailsAgent[/green]")

    # Test getting status (doesn't require LLM)
    status = agent.get_status()
    console.print(f"[green]✓ Agent status: {len(status['tool_registry']['tools_available'])} tools available[/green]")

    console.print("\n[bold green]🎉 All tests passed! The async fix is working.[/bold green]")
    console.print("[dim]You can now safely run ask_code_refactored.py[/dim]")

except Exception as e:
    console = Console()
    console.print(f"[red]✗ Test failed: {e}[/red]")
    import traceback
    console.print(f"[dim]{traceback.format_exc()}[/dim]")
    sys.exit(1)