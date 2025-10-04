"""Spinner management for LLM clients with soft fade animation."""

from __future__ import annotations

import logging
import random
import threading
from itertools import cycle
from typing import Optional

from rich.console import Console
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

logger = logging.getLogger(__name__)


class SpinnerManager:
    """Manages an animated spinner with a subtle fade-in/out effect."""

    _RANDOM_MESSAGES = [
        "Gibberish……",
        "Abracadabra……",
        "Fiddle-faddle……",
        "Mumbo jumbo……",
        "Jabberwocky……",
    ]

    def __init__(
        self,
        console: Optional[Console] = None,
        style: str = "dots",
        color: str = "yellow",
        refresh_rate: int = 12,
    ) -> None:
        self.console = console or Console()
        self.style = style
        self.color = color
        self.refresh_rate = refresh_rate

        self._spinner_live: Optional[Live] = None
        self._spinner_renderable: Optional[Spinner] = None
        self._is_active = False
        self._fade_thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._current_message: str = ""

    # ------------------------------------------------------------------
    def start(self, message: Optional[str] = None) -> None:
        """Start the spinner and kick off the fade animation."""
        if self._is_active:
            return

        display_message = message or random.choice(self._RANDOM_MESSAGES)
        self._current_message = display_message

        try:
            spinner = Spinner(self.style, text=Text(display_message), style=self.color)
            self._spinner_renderable = spinner
            self._spinner_live = Live(
                spinner,
                console=self.console,
                refresh_per_second=self.refresh_rate,
                transient=True,
            )
            self._spinner_live.start()
            self._is_active = True

            self._stop_event = threading.Event()
            fade_cycle = cycle(["dim", "", "bold"])

            def _animate() -> None:
                while self._stop_event and not self._stop_event.is_set():
                    try:
                        style_token = next(fade_cycle)
                        if self._spinner_renderable:
                            styled_text = Text(
                                self._current_message,
                                style=style_token or None,
                            )
                            self._spinner_renderable.text = styled_text
                            if self._spinner_live:
                                self._spinner_live.update(self._spinner_renderable)
                    except Exception as animation_error:  # pragma: no cover - defensive
                        logger.debug(f"Spinner animation error: {animation_error}")
                    finally:
                        if self._stop_event and not self._stop_event.wait(0.55):
                            continue
                        break

            self._fade_thread = threading.Thread(
                target=_animate,
                name="SpinnerFadeThread",
                daemon=True,
            )
            self._fade_thread.start()

        except Exception as error:
            logger.debug(f"Could not start spinner: {error}")
            self.console.print(f"[dim]{display_message}[/dim]")

    # ------------------------------------------------------------------
    def stop(self) -> None:
        """Stop the spinner, animation thread, and clear the line."""
        if self._stop_event:
            self._stop_event.set()

        if self._fade_thread and self._fade_thread.is_alive():
            self._fade_thread.join(timeout=0.5)

        self._fade_thread = None
        self._stop_event = None

        if self._spinner_live:
            try:
                self._spinner_live.stop()
            except Exception as error:
                logger.debug(f"Error stopping spinner: {error}")
            finally:
                self._spinner_live = None

        try:
            stream = getattr(self.console, "file", None)
            if stream is None:
                import sys

                stream = sys.stderr

            stream.write("\r\033[K")
            stream.flush()
        except Exception as error:
            logger.debug(f"Error clearing spinner line: {error}")

        self._spinner_renderable = None
        self._is_active = False

    # ------------------------------------------------------------------
    def update_message(self, message: str) -> None:
        """Update spinner message, preserving animation."""
        if not self._is_active or not self._spinner_live or not self._spinner_renderable:
            return

        try:
            self._current_message = message
            self._spinner_renderable.text = Text(message)
            self._spinner_live.update(self._spinner_renderable)
        except Exception as error:
            logger.debug(f"Error updating spinner message: {error}")

    # ------------------------------------------------------------------
    def is_active(self) -> bool:
        return self._is_active

    # ------------------------------------------------------------------
    def __enter__(self) -> "SpinnerManager":
        return self

    # ------------------------------------------------------------------
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()

    # ------------------------------------------------------------------
    def __del__(self) -> None:
        self.stop()
