"""Input handling utilities."""

import sys
from contextlib import contextmanager
from typing import Optional


@contextmanager
def _raw_mode(file):
    """Best-effort cbreak mode so single-key presses are readable without Enter.

    No-ops on non-TTYs or platforms without termios/tty.
    """
    try:
        import termios  # type: ignore
        import tty  # type: ignore
    except Exception:
        # Unsupported platform or import error; proceed without raw mode
        yield
        return

    old_attrs = None
    try:
        # Skip raw mode for non-TTY files (pipes, redirects)
        if not hasattr(file, "isatty") or not file.isatty():
            yield
            return
        fd = file.fileno()
        # Save current terminal attributes for restoration
        old_attrs = termios.tcgetattr(fd)
        # Enable character-break mode (single char input without buffering)
        tty.setcbreak(fd)
        yield
    except Exception:
        # Let the exception bubble up after restoring terminal
        raise
    finally:
        # Always restore original terminal settings if they were saved
        if old_attrs is not None:
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
            except Exception:
                pass  # Ignore restore errors


def _esc_pressed(timeout: float = 0.0) -> bool:
    """Return True if ESC was pressed within timeout seconds.

    Uses select+os.read in a non-blocking way; returns False on non-TTY or unsupported platforms.
    """
    try:
        import select
        import os as _os
    except Exception:
        return False
    # Only works on TTY (not pipes/redirects)
    if not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
        return False
    try:
        # Check if stdin has data available within timeout
        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            # Read single byte and check if it's ESC (0x1b)
            ch = _os.read(sys.stdin.fileno(), 1)
            return ch == b"\x1b"  # ESC
    except Exception:
        return False
    return False


def should_exit_from_input(user_input: Optional[str]) -> bool:
    """Check if user input indicates they want to exit."""
    if user_input == "__EXIT__":
        return True
    if user_input and user_input.strip().lower() == "/exit":
        return True
    return False