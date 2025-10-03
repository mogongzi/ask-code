#!/usr/bin/env python3
"""
Demo different spinner styles available in the BlockingClient.

Run this to see various spinner animations you can use.
"""
import time
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

def demo_spinner_styles():
    """Show different spinner styles available."""
    console = Console()

    # Available spinner styles in Rich
    spinner_styles = [
        ("dots", "Default - smooth rotating dots"),
        ("line", "Simple line spinner"),
        ("simpleDotsScrolling", "Scrolling dots"),
        ("arc", "Arc/circle animation"),
        ("arrow3", "Rotating arrow"),
        ("bouncingBar", "Bouncing progress bar"),
        ("circleHalves", "Rotating circle halves"),
        ("dots12", "12-dot circle"),
        ("aesthetic", "Aesthetic unicode spinner"),
        ("moon", "Moon phases"),
    ]

    console.print("[bold cyan]Spinner Style Demo[/bold cyan]\n")
    console.print("Showing various spinner animations (2 seconds each):\n")

    for style, description in spinner_styles:
        console.print(f"[bold]{style}[/bold]: {description}")

        spinner = Spinner(style, text=f"Testing {style} spinner...", style="yellow")

        with Live(spinner, console=console, refresh_per_second=10):
            time.sleep(2)

        console.print("[green]✓ Done[/green]\n")

    console.print("\n[bold green]Demo complete![/bold green]")
    console.print("\nTo use a different spinner style, modify [cyan]blocking_client.py[/cyan]:")
    console.print('[dim]spinner = Spinner("dots", text=message, style="yellow")[/dim]')
    console.print('[dim]                   ^^^^[/dim]')
    console.print('[dim]            Change this to any style above[/dim]')

if __name__ == "__main__":
    demo_spinner_styles()