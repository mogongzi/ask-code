#!/usr/bin/env python3
"""
Advanced multi-line input system using prompt-toolkit.

This module provides a sophisticated multi-line input interface with:
- Visual ▌ cursor indicator on every line
- Enter key for submission
- Ctrl+J for adding new lines
- Ctrl+J for adding new lines
- Consistent cross-platform behavior

Key Features:
    - Enter = Submit message
    - Ctrl+J = Add new line
    - Ctrl+J = Add new line for multi-line input
    - ▌ cursor appears on every line for visual consistency
"""
from __future__ import annotations

from typing import Optional

from prompt_toolkit import prompt
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.filters import Condition
from prompt_toolkit.application.current import get_app
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import merge_completers
from prompt_toolkit.styles import Style
from rich.console import Console
from util.at_completer import AtCommandCompleter

# Constants for visual consistency
CURSOR_CHARACTER = "▌"


def get_multiline_input(
    console: Console,
    prompt_style: str = "bold green",
    token_info: Optional[str] = None,
    thinking_mode: bool = False,
    history: Optional[list[str]] = None,
    tools_enabled: bool = False,
    agent_enabled: bool = False,
    context_manager=None
) -> tuple[Optional[str], bool, bool, bool]:
    """
    Get multi-line input from user with enhanced prompt-toolkit interface.

    This function provides a sophisticated input experience with:
    - Visual cursor indicator (▌) on every line
    - Enter key submits the complete input
    - Ctrl+J adds new lines for multi-line messages
    - Ctrl+J for multi-line input support
    - Consistent escape/cancellation behavior

    Args:
        console: Rich console instance for displaying messages and styling
        prompt_style: Style string for prompt formatting (currently unused
                     but kept for API compatibility)
        token_info: Optional token usage string to display (e.g., "1.2k/200k (0.6%)")
        thinking_mode: Current thinking mode state (ON/OFF)
        history: Optional list of previous user inputs for up/down navigation
        tools_enabled: Current tools mode state (ON/OFF)
        agent_enabled: Current ReAct agent mode state (ON/OFF)
        context_manager: Optional context manager for @ command autocompletion

    Returns:
        tuple[Optional[str], bool, bool, bool]: (user_input, use_thinking, new_thinking_mode, new_tools_enabled)

    Raises:
        No exceptions are raised - all errors are caught and handled gracefully

    Examples:
        >>> console = Console()
        >>> user_input = get_multiline_input(console)
        >>> if user_input:
        ...     print(f"User entered: {user_input}")
    """
    key_bindings = _create_key_bindings(history or [])

    # Show instructions with token info before prompting
    _display_usage_instructions(console, token_info, thinking_mode, tools_enabled, agent_enabled)

    try:
        user_input = _prompt_for_input(key_bindings, history, context_manager)

        # Check for empty input immediately to avoid any visual artifacts
        # But allow @ commands through (including just "@")
        if not user_input:
            return None, False, thinking_mode, tools_enabled

        stripped_input = user_input.strip()
        # Allow @ commands through, even if just "@"
        if stripped_input.startswith('@'):
            # Check if this is a complete file path (from autocomplete selection)
            if _is_complete_at_command(stripped_input, context_manager):
                # Automatically add file to context and return empty to continue input
                _handle_at_selection(stripped_input, context_manager, console)
                return None, False, thinking_mode, tools_enabled
            else:
                # Process as regular @ command (for manual entry or incomplete paths)
                return _process_user_input(user_input, console, thinking_mode, tools_enabled)

        # Check for other empty input
        if not stripped_input:
            return None, False, thinking_mode, tools_enabled

        return _process_user_input(user_input, console, thinking_mode, tools_enabled)

    except (KeyboardInterrupt, EOFError):
        _display_cancellation_message(console)
        return "__EXIT__", False, thinking_mode, tools_enabled  # Special exit signal


def _create_key_bindings(history: list[str] = None) -> KeyBindings:
    """
    Create and configure key bindings for the input interface.

    Sets up custom key combinations to override prompt-toolkit's default
    multiline behavior, allowing us to control when input is submitted
    versus when new lines are added. Also includes history navigation.

    Args:
        history: List of previous user inputs for up/down arrow navigation

    Returns:
        KeyBindings: Configured key bindings object for prompt-toolkit
    """
    bindings = KeyBindings()

    # History navigation state
    if history is None:
        history = []

    history_position = len(history)  # Start at end (no selection)
    original_text = ""  # Store original text when navigating

    # Completion menu filters
    @Condition
    def completion_menu_inactive() -> bool:
        try:
            return get_app().current_buffer.complete_state is None
        except Exception:
            return True

    @Condition
    def completion_menu_active() -> bool:
        return not completion_menu_inactive()

    # When menu is active, Enter accepts the completion and, if a folder was chosen,
    # immediately reopens completion in that folder.
    @bindings.add('enter', eager=True, filter=completion_menu_active)
    def handle_enter_accept_completion(event):
        buf = event.current_buffer
        state = buf.complete_state
        if state and state.current_completion:
            comp = state.current_completion
            buf.apply_completion(comp)
            # If the accepted text ends with '/', keep browsing
            try:
                before = buf.document.text_before_cursor
            except Exception:
                before = buf.text
            if before.strip().endswith('/'):
                buf.start_completion(select_first=True)
                return
            # Otherwise, this looks like a file: submit immediately so it's added to context
            event.app.exit(result=buf.text)
        # No further action; binding is eager so Enter won't submit.

    @bindings.add('enter', eager=True, filter=completion_menu_inactive)
    def handle_enter_key_submission(event):
        """Handle Enter key press - submit the current input only if non-empty."""
        current_text = event.current_buffer.text
        # Only submit if there's actual content (not just whitespace)
        if current_text and current_text.strip():
            event.app.exit(result=current_text)
        # If empty or whitespace only, do nothing (don't exit, don't add newline)

    @bindings.add('c-j', eager=True)
    def handle_ctrl_j_new_line(event):
        """Handle Ctrl+J key press - add a new line to current input."""
        event.current_buffer.insert_text('\n')

    @bindings.add('c-c')
    def handle_ctrl_c_cancellation(event):
        """Handle Ctrl+C key press - cancel input and return None."""
        event.app.exit(result=None)

    @bindings.add('escape', eager=True)
    def handle_escape_cancellation(event):
        """Handle Escape key press - cancel input and return None."""
        event.app.exit(result=None)

    @bindings.add('up', filter=completion_menu_inactive)
    def handle_up_arrow_history(event):
        """Handle Up arrow key press - navigate to previous history item."""
        nonlocal history_position, original_text

        if not history:
            return  # No history to navigate

        # Save original text when first navigating
        if history_position == len(history):
            original_text = event.current_buffer.text

        # Move up in history (towards older entries)
        if history_position > 0:
            history_position -= 1
            event.current_buffer.text = history[history_position]
            event.current_buffer.cursor_position = len(history[history_position])

    @bindings.add('down', filter=completion_menu_inactive)
    def handle_down_arrow_history(event):
        """Handle Down arrow key press - navigate to next history item."""
        nonlocal history_position, original_text

        if not history:
            return  # No history to navigate

        # Move down in history (towards newer entries)
        if history_position < len(history):
            history_position += 1

            if history_position == len(history):
                # Back to original/empty text
                event.current_buffer.text = original_text
                event.current_buffer.cursor_position = len(original_text)
            else:
                event.current_buffer.text = history[history_position]
                event.current_buffer.cursor_position = len(history[history_position])


    return bindings


def _display_usage_instructions(console: Console, token_info: Optional[str] = None, thinking_mode: bool = False, tools_enabled: bool = False, agent_enabled: bool = False, show_instructions: bool = True) -> None:
    """
    Display usage instructions to help user understand key bindings.

    Args:
        console: Rich console instance for styled output
        token_info: Optional token usage string to display on the right side
        thinking_mode: Whether thinking mode is currently enabled
        tools_enabled: Whether tools mode is currently enabled
        agent_enabled: Whether ReAct agent mode is currently enabled (deprecated, ignored)
        show_instructions: Whether to show the usage instructions
    """
    # Build instructions with status indicators
    base_instructions = "↵ send    Ctrl+J newline"

    # Add thinking mode status
    if thinking_mode:
        thinking_part = "/think reasoning [ON]"
    else:
        thinking_part = "/think reasoning"

    # Add tools mode status
    if tools_enabled:
        tools_part = "/tools functions [ON]"
    else:
        tools_part = "/tools functions"

    # Agent mode is deprecated - no longer shown
    instructions = f"{base_instructions}    {thinking_part}    {tools_part}    Esc/Ctrl+C=cancel"

    # Only show instructions if requested
    if not show_instructions:
        # Show only token info if available
        if token_info:
            console.print(f"[dim]Tokens: {token_info}[/dim]")
        return

    if token_info:
        # Calculate padding to right-align token info
        terminal_width = console.size.width
        base_length = len(instructions)  # Use actual instruction text length
        token_length = len(f"Tokens: {token_info}")
        padding_needed = terminal_width - base_length - token_length - 4  # 4 for spacing buffer

        if padding_needed > 0:
            padding = " " * padding_needed
            full_line = f"{instructions}{padding}Tokens: {token_info}"
        else:
            # Fallback if terminal too narrow
            full_line = f"{instructions}  Tokens: {token_info}"
    else:
        full_line = instructions

    console.print(f"[dim]{full_line}[/dim]")


def _create_prompt_functions():
    """
    Create prompt functions for consistent cursor display.

    Returns:
        tuple: (main_prompt_function, continuation_prompt_function)
    """
    def get_main_prompt():
        """Return the main prompt string with cursor character."""
        return HTML(f'<lemonchiffon>{CURSOR_CHARACTER}</lemonchiffon> ')

    def get_continuation_prompt(width, line_number, is_soft_wrap):
        """
        Return the continuation prompt for multi-line input.

        Args:
            width: Terminal width (unused but required by prompt-toolkit)
            line_number: Current line number (unused but required)
            is_soft_wrap: Whether this is a soft wrap (unused but required)

        Returns:
            str: Same cursor character for visual consistency
        """
        return HTML(f'<lemonchiffon>{CURSOR_CHARACTER}</lemonchiffon> ')

    return get_main_prompt, get_continuation_prompt


def _prompt_for_input(key_bindings: KeyBindings, history: list[str] = None, context_manager=None) -> str:
    """
    Execute the actual prompt-toolkit input session.

    Args:
        key_bindings: Pre-configured key bindings for the input session
        history: List of previous inputs for history navigation
        context_manager: Optional context manager for @ command autocompletion

    Returns:
        str: Raw user input from prompt-toolkit
    """
    main_prompt, continuation_prompt = _create_prompt_functions()

    # Create @ command completer if context manager is available
    completer = None
    if context_manager:
        completer = AtCommandCompleter(context_manager=context_manager)

    # Simple, minimal completion menu theme to match main UI
    minimal_style = Style.from_dict({
        # Completion menu colors
        "completion-menu": "bg:#2b2b2b #e5e5e5",
        "completion-menu.completion": "bg:#2b2b2b #e5e5e5",
        "completion-menu.completion.current": "bg:#3a3a3a #ffffff",
        # Scrollbar
        "scrollbar.background": "bg:#2b2b2b",
        "scrollbar.button": "bg:#555555",
    })

    return prompt(
        main_prompt,
        key_bindings=key_bindings,
        multiline=True,
        wrap_lines=True,
        prompt_continuation=continuation_prompt,
        completer=completer,
        complete_while_typing=True,  # Enable live completion
        style=minimal_style,
    )


def _process_user_input(user_input: str, console: Console, thinking_mode: bool, tools_enabled: bool) -> tuple[Optional[str], bool, bool, bool]:
    """
    Process the raw user input and handle special commands.

    Args:
        user_input: Raw input string from prompt-toolkit
        console: Rich console instance for any needed output
        thinking_mode: Current thinking mode state
        tools_enabled: Current tools mode state

    Returns:
        tuple[Optional[str], bool, bool, bool]: (processed_input, use_thinking, new_thinking_mode, new_tools_enabled)
    """
    # Input is guaranteed to be non-empty by caller
    cleaned_input = user_input.strip()

    # Handle @ commands for file browsing - these need special processing
    if cleaned_input.startswith('@'):
        return f"__AT_COMMAND__{cleaned_input}", False, thinking_mode, tools_enabled  # Special @ command signal

    # Handle thinking mode toggle command
    if cleaned_input == '/think':
        if thinking_mode:
            console.print("[dim]Thinking mode disabled.[/dim]")
        else:
            console.print("[green]Thinking mode enabled. All messages will now show reasoning.[/green]")
        return None, False, not thinking_mode, tools_enabled  # Toggle thinking mode

    # Handle tools mode toggle command
    elif cleaned_input == '/tools':
        if tools_enabled:
            console.print("[dim]Tools disabled. Claude will not use function calls.[/dim]")
        else:
            console.print("[green]Tools enabled. Claude can now use time tool.[/green]")
        return None, False, thinking_mode, not tools_enabled  # Toggle tools mode

    # Handle clear command
    elif cleaned_input == '/clear':
        console.print("[green]Chat history cleared.[/green]")
        return "__CLEAR__", False, thinking_mode, tools_enabled  # Special clear signal

    # Handle legacy /think <message> format for backward compatibility
    elif cleaned_input.startswith('/think '):
        actual_message = cleaned_input[7:].strip()  # Remove "/think " prefix
        if actual_message:
            console.print("[dim]Tip: Use /think to toggle thinking mode on/off, then just type your message.[/dim]")
            return actual_message, True, thinking_mode, tools_enabled
        else:
            console.print("[yellow]Use /think to toggle thinking mode on/off, or /think <message> for one-time thinking.[/yellow]")
            return None, False, thinking_mode, tools_enabled

    # Regular message - use current thinking mode
    if cleaned_input:
        return cleaned_input, thinking_mode, thinking_mode, tools_enabled
    else:
        return None, False, thinking_mode, tools_enabled


def _is_complete_at_command(at_command: str, context_manager) -> bool:
    """Check if @ command refers to a complete file path that should be added to context.

    Args:
        at_command: The @ command string (e.g., "@file.txt")
        context_manager: Context manager instance

    Returns:
        True if this is a complete file that should be auto-added to context
    """
    if not at_command.startswith('@'):
        return False

    file_path = at_command[1:]  # Remove @ prefix

    # Don't auto-add if it's just "@" or ends with "/"
    if not file_path or file_path.endswith('/'):
        return False

    # Check if it's a valid file path
    import os
    try:
        # Resolve path
        if file_path.startswith('~/'):
            resolved_path = os.path.expanduser(file_path)
        elif file_path.startswith('./'):
            resolved_path = os.path.abspath(file_path)
        elif os.path.isabs(file_path):
            resolved_path = file_path
        else:
            resolved_path = os.path.join(os.getcwd(), file_path)

        # Check if it's a readable file
        return os.path.isfile(resolved_path) and os.access(resolved_path, os.R_OK)
    except:
        return False


def _handle_at_selection(at_command: str, context_manager, console: Console) -> None:
    """Handle automatic addition of file to context from @ autocomplete selection.

    Args:
        at_command: The @ command string (e.g., "@file.txt")
        context_manager: Context manager instance
        console: Rich console for output
    """
    if not context_manager:
        return

    file_path = at_command[1:]  # Remove @ prefix

    try:
        # Add file to context
        context_manager.add_file_context(file_path)

        # Get relative path for display
        import os
        try:
            rel_path = os.path.relpath(file_path)
            display_path = rel_path if len(rel_path) < len(file_path) else file_path
        except ValueError:
            display_path = file_path

        console.print(f"[green]Added context file: {display_path}[/green]")
        console.print(f"[dim]Context status: {context_manager.get_status_summary()}[/dim]")

    except ValueError as e:
        console.print(f"[red]Error adding context: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")


def _display_cancellation_message(console: Console) -> None:
    """
    Display a user-friendly cancellation message.

    Args:
        console: Rich console instance for styled output
    """
    console.print("\n[dim]Cancelled[/dim]")
