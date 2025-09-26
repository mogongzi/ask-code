from __future__ import annotations

import io
import time
from dataclasses import dataclass, field
from typing import List, Optional

from rich import box
from rich.console import Console
from rich.live import Live
from rich.markdown import CodeBlock, Heading, Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.spinner import Spinner


class _CodeBlockTight(CodeBlock):
    def __rich_console__(self, console, options):
        code = str(self.text).rstrip()
        syntax = Syntax(code, self.lexer_name, theme=self.theme, word_wrap=True, padding=(1, 0))
        yield syntax


class _HeadingLeft(Heading):
    def __rich_console__(self, console, options):
        text = self.text
        text.justify = "left"
        if self.tag == "h1":
            yield Panel(text, box=box.HEAVY, style="markdown.h1.border")
        else:
            if self.tag == "h2":
                yield Text("")
            yield text


class MarkdownStyled(Markdown):
    elements = {
        **Markdown.elements,
        "fence": _CodeBlockTight,
        "code_block": _CodeBlockTight,
        "heading_open": _HeadingLeft,
    }


@dataclass
class MarkdownStream:
    live: Optional[Live] = None
    when: float = 0.0
    min_delay: float = 1.0 / 20
    live_window: int = 6
    printed: List[str] = field(default_factory=list)
    waiting_active: bool = False
    waiting_message: str = ""
    thinking_buffer: List[str] = field(default_factory=list)
    response_buffer: List[str] = field(default_factory=list)
    in_thinking_phase: bool = False
    thinking_printed: bool = False

    def _render_md_lines(self, text: str) -> List[str]:
        buf = io.StringIO()
        tmp = Console(file=buf, force_terminal=True)
        tmp.print(MarkdownStyled(text))
        return buf.getvalue().splitlines(keepends=True)

    def _ensure_live(self):
        if not self.live:
            self.live = Live(Text(""), refresh_per_second=1.0 / self.min_delay)
            self.live.start()

    def stop(self):
        if self.live:
            try:
                self.live.update(Text(""))
                self.live.stop()
            except Exception:
                pass
            self.live = None

    def start_waiting(self, message: str = "Waiting for response…") -> None:
        """Show a distinct animated waiting indicator inside the live area.

        Uses a spinner + dim italic message, clearly different from model output.
        """
        if self.waiting_active:
            return
        self._ensure_live()
        self.waiting_active = True
        self.waiting_message = message
        spinner = Spinner("dots", text=Text(message, style="dim italic"), style="yellow")
        if self.live:
            self.live.update(spinner)
            self.live.refresh()

    def stop_waiting(self) -> None:
        if not self.waiting_active:
            return
        self.waiting_active = False
        self.waiting_message = ""
        if self.live:
            try:
                # Clear Live region fully and refresh so previous spinner text is removed
                self.live.update(Text(""))
                self.live.refresh()
            except Exception:
                pass
        # Reset pacing so the next content update isn't throttled
        self.when = 0.0

    def update(self, cumulative_text: str, final: bool = False) -> None:
        self._ensure_live()

        now = time.time()
        if not final and (now - self.when) < self.min_delay:
            return
        self.when = now

        t0 = time.time()
        lines = self._render_md_lines(cumulative_text)
        render_time = time.time() - t0
        self.min_delay = min(max(render_time * 10, 1.0 / 20), 2)

        total = len(lines)
        stable = total if final else max(0, total - self.live_window)

        # If waiting indicator is active and we now have any content, stop it
        if self.waiting_active and total > 0:
            self.stop_waiting()

        # While waiting and no content yet, keep the spinner visible
        if self.waiting_active and total == 0 and not final:
            return

        if final or stable > 0:
            already = len(self.printed)
            need = stable - already
            if need > 0:
                chunk = "".join(lines[already:stable])
                if self.live:
                    self.live.console.print(Text.from_ansi(chunk))
                    self.printed = lines[:stable]

        if final:
            self.stop()
            return

        tail = "".join(lines[stable:])
        if self.live:
            self.live.update(Text.from_ansi(tail))

    def add_thinking(self, text: str) -> None:
        """Add thinking text and render it streamingly with Claude Code style."""
        if not self.in_thinking_phase:
            self.in_thinking_phase = True
            self.thinking_buffer = ["*Thinking...*\n\n"]
            # Print header immediately
            self._ensure_live()
            header = self._render_md_lines("*Thinking...*\n")
            if self.live:
                self.live.console.print(Text.from_ansi("".join(header), style="dim italic"))

        self.thinking_buffer.append(text)
        self._stream_thinking()

    def add_response(self, text: str) -> None:
        """Add response text and render it normally."""
        if self.in_thinking_phase:
            self._finalize_thinking()
            self.in_thinking_phase = False

        self.response_buffer.append(text)
        # Use existing update logic for streaming response
        self.update("".join(self.response_buffer), final=False)

    def _stream_thinking(self) -> None:
        """Stream thinking content in real-time with dim italic style."""
        self._ensure_live()

        # Get current thinking content (skip header)
        current_thinking = "".join(self.thinking_buffer[1:])  # Skip "*Thinking...*\n\n"

        if current_thinking:
            # Apply same streaming logic as normal content
            now = time.time()
            if (now - self.when) < self.min_delay:
                return
            self.when = now

            # Render and display thinking content
            lines = self._render_md_lines(current_thinking)
            tail_content = "".join(lines[-self.live_window:])  # Show live window

            # Display with dim italic style
            styled_text = Text.from_ansi(tail_content, style="dim italic")
            if self.live:
                self.live.update(styled_text)

    def _finalize_thinking(self) -> None:
        """Finalize thinking section and prepare for response."""
        if self.in_thinking_phase and self.live:
            # Print final thinking content
            current_thinking = "".join(self.thinking_buffer[1:])
            if current_thinking:
                lines = self._render_md_lines(current_thinking)
                final_content = "".join(lines)
                self.live.console.print(Text.from_ansi(final_content, style="dim italic"))

            # Add separator line
            self.live.console.print(Text(""))

            # Reset live area for response
            self.live.update(Text(""))
