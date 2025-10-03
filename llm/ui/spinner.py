"""
Spinner management for LLM clients.

Separates UI concerns from business logic.
"""

from __future__ import annotations

import logging
from typing import Optional
from rich.console import Console
from rich.spinner import Spinner
from rich.live import Live

logger = logging.getLogger(__name__)


class SpinnerManager:
    """Manages animated spinner lifecycle.

    Encapsulates spinner creation, start/stop logic, and error handling.
    This separates UI concerns from client business logic.
    """

    def __init__(
        self,
        console: Optional[Console] = None,
        style: str = "dots",
        color: str = "yellow",
        refresh_rate: int = 10
    ):
        """Initialize spinner manager.

        Args:
            console: Rich console for output
            style: Spinner style (dots, line, arc, etc.)
            color: Spinner color
            refresh_rate: Refresh rate in FPS
        """
        self.console = console or Console()
        self.style = style
        self.color = color
        self.refresh_rate = refresh_rate
        self._spinner_live: Optional[Live] = None
        self._is_active = False

    def start(self, message: str = "Waiting for response…") -> None:
        """Start animated spinner.

        Args:
            message: Message to display with spinner
        """
        if self._is_active:
            return

        try:
            spinner = Spinner(self.style, text=message, style=self.color)
            self._spinner_live = Live(
                spinner,
                console=self.console,
                refresh_per_second=self.refresh_rate
            )
            self._spinner_live.start()
            self._is_active = True

        except Exception as e:
            logger.debug(f"Could not start spinner: {e}")
            # Fallback to simple message
            self.console.print(f"[dim]{message}[/dim]")

    def stop(self) -> None:
        """Stop animated spinner and clear the line."""
        # Always try to stop, regardless of _is_active state
        # This handles edge cases where state tracking gets out of sync
        if self._spinner_live:
            try:
                # Stop the Live context
                self._spinner_live.stop()
            except Exception as e:
                logger.debug(f"Error stopping spinner: {e}")
            finally:
                self._spinner_live = None

        # Clear the spinner line to ensure it's fully removed
        # This must happen AFTER stopping Live to properly clear the output
        try:
            # Use Rich's file attribute which handles the proper stream
            # Rich.Live uses console.file (usually stderr by default)
            if hasattr(self.console, 'file'):
                stream = self.console.file
            else:
                import sys
                stream = sys.stderr

            # Write ANSI clear code directly to the stream
            stream.write('\r\033[K')
            stream.flush()
        except Exception as e:
            logger.debug(f"Error clearing spinner line: {e}")

        # Reset state
        self._is_active = False

    def update_message(self, message: str) -> None:
        """Update spinner message without restarting.

        Args:
            message: New message to display
        """
        if self._is_active and self._spinner_live:
            try:
                spinner = Spinner(self.style, text=message, style=self.color)
                self._spinner_live.update(spinner)
            except Exception as e:
                logger.debug(f"Error updating spinner: {e}")

    def is_active(self) -> bool:
        """Check if spinner is currently active.

        Returns:
            True if spinner is running
        """
        return self._is_active

    def __enter__(self) -> SpinnerManager:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - always stop spinner."""
        self.stop()

    def __del__(self) -> None:
        """Ensure spinner is stopped on cleanup."""
        self.stop()