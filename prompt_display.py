from prompt_toolkit import Application
from prompt_toolkit.layout.containers import HSplit, Window, Container
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import ANSI
from rich.console import Console
from io import StringIO
import asyncio

# --- 1. Rich Content Conversion Utility ---


def get_rich_formatted_text(rich_renderable):
    """
    Renders a rich object to ANSI and converts it to prompt_toolkit's FormattedText.
    """
    # Create a Console pointing to a StringIO to capture the output as ANSI codes
    capture = StringIO()
    console = Console(file=capture, force_terminal=True, color_system="truecolor")

    # Use rich to print and style your string
    console.print(rich_renderable, markup=True, highlight=True, end="")

    # Return the ANSI codes wrapped in prompt_toolkit's ANSI object
    return ANSI(capture.getvalue())


# --- 2. Build the Custom Layout ---


def create_input_and_message_layout(input_buffer: Buffer) -> Container:
    """
    Creates an HSplit layout with the input buffer on top and a rich-styled message below.
    """

    # 1. The input prompt line (like "Searching for log location...")
    prompt_control = FormattedTextControl(
        [("class:prompt", "Searching for log location (23s • Esc to interrupt)\n")]
    )
    prompt_window = Window(content=prompt_control, height=1)

    # 2. The editable input area (the blank line with the cursor)
    input_control = BufferControl(buffer=input_buffer)
    input_window = Window(content=input_control, height=1, char=" ")

    # 3. The rich-styled message/status area (like "Enter send | ^J newline...")
    rich_styled_message = get_rich_formatted_text(
        "[bold cyan]Enter[/bold cyan] send | [bold yellow]^J[/bold yellow] newline | [bold red]^C[/bold red] quit"
        " | [green]339K tokens used[/green] | [green]79% context left[/green]"
    )
    message_control = FormattedTextControl(rich_styled_message)
    # The message should only take one line, so height=1
    message_window = Window(content=message_control, height=1)

    # Put them all in a vertical stack (HSplit).
    # They will stack right where the Application starts, not at the bottom of the terminal.
    return HSplit(
        [
            prompt_window,
            input_window,
            message_window,
            # Add a placeholder to let the prompt stay in the upper part of the screen
            Window(height=None),
        ]
    )


# --- 3. Main Application Logic ---


async def main():
    # The Buffer holds the text being edited by the user.
    input_buffer = Buffer()

    # Create key bindings
    kb = KeyBindings()

    @kb.add("enter")
    def _(event):
        # When the user presses Enter, exit and return the text.
        event.app.exit(result=input_buffer.text)

    @kb.add("c-c")
    def _(event):
        # Handle Ctrl+C to quit
        event.app.exit(result=None)

    # Create the custom layout
    root_container = create_input_and_message_layout(input_buffer)

    # Create and run the application
    application = Application(
        layout=Layout(root_container, focused_element=input_buffer),
        key_bindings=kb,
        full_screen=False,  # Crucial: This makes it a shell-like prompt, not a fullscreen editor
    )

    # Run the application to get the user input
    result = await application.run_async()

    print(
        f"\nCommand received: {result}"
        if result is not None
        else "\nOperation cancelled."
    )


if __name__ == "__main__":
    asyncio.run(main())
