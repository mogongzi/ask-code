"""Command handling utilities for special commands."""

from typing import Optional
from context.context_manager import ContextManager
from util.path_browser import PathBrowser


def show_help_message(console) -> None:
    """Display help message with all available commands."""
    console.print("\n[bold cyan]Available Commands:[/bold cyan]")
    console.print("  [bold green]/help[/bold green]         - Show this help message")
    console.print("  [bold green]/clear[/bold green]        - Clear conversation history")
    console.print("  [bold green]/context[/bold green] <file> - Add file context to conversation")
    console.print("  [bold green]/context clear[/bold green] - Remove all file context")
    console.print("  [bold green]/context list[/bold green]  - Show active context files")
    console.print("  [bold green]/exit[/bold green]         - Quit the program")
    console.print()
    console.print("[bold cyan]RAG Commands:[/bold cyan]")
    console.print("  [bold green]/rag index[/bold green] <type> <path> - Build index (type: naive)")
    console.print("  [bold green]/rag search[/bold green] <query> [k] - Preview top-k snippets")
    console.print("  [bold green]/rag on[/bold green] | /rag off - Toggle retrieval on submit")
    console.print("  [bold green]/rag status[/bold green]          - Show index status")
    console.print("  [bold green]/rag clear[/bold green]           - Remove saved index")
    console.print()
    console.print("[bold cyan]Rails Code Analysis:[/bold cyan]")
    console.print("  [bold green]ride_rails.py[/bold green] --project <path> - Dedicated Rails analysis tool")
    console.print("  [dim]Example: python ride_rails.py --project /path/to/rails/app[/dim]")
    console.print("  [bold green]/tools[/bold green]          - Show agent tools and CLI availability")
    console.print()
    console.print("[bold cyan]Session Commands:[/bold cyan]")
    console.print("  [bold green]/save[/bold green] [path]        - Save session JSON to file (default logs/sessions/<id>/session.json)")
    console.print("  [bold green]/export md[/bold green] [path]   - Export Markdown transcript (default logs/sessions/<id>/export.md)")
    console.print("  [bold green]/session status[/bold green]     - Show session id, totals, and folder")
    console.print()
    console.print("[bold cyan]@ File Browser Commands:[/bold cyan]")
    console.print("  [bold yellow]@[/bold yellow]            - Start file path and use dropdown")
    console.print("  [bold yellow]@/path/[/bold yellow]      - Navigate into folder (dropdown)")
    console.print("  [bold yellow]@~/[/bold yellow]          - Browse home (dropdown)")
    console.print("  [bold yellow]@file.txt[/bold yellow]    - Add file to context")
    console.print()
    console.print("[bold cyan]Keyboard Shortcuts:[/bold cyan]")
    console.print("  [bold yellow]Ctrl+J[/bold yellow]     - Insert new line (in multi-line input)")
    console.print("  [bold yellow]Enter[/bold yellow]      - Send message")
    console.print("  [bold yellow]Esc[/bold yellow]        - Abort current stream")
    console.print("  [bold yellow]Ctrl+C[/bold yellow]     - Quit program")
    console.print()
    console.print("[bold cyan]Features:[/bold cyan]")
    console.print("  • Live Markdown rendering with syntax highlighting")
    console.print("  • Tool calling support (toggle with tools indicator)")
    console.print("  • Thinking mode support (toggle with thinking indicator)")
    console.print("  • File context injection for enhanced conversations")
    console.print("  • Interactive file browser with @ commands")
    console.print("  • Token usage and cost tracking")
    console.print("  • Input history navigation")
    console.print()


def handle_special_commands(user_input: Optional[str], conversation, console=None, context_manager: Optional[ContextManager] = None, path_browser: Optional[PathBrowser] = None, rag_manager=None, react_agent=None) -> bool:
    """Handle special commands like /help, /clear, /context, @ and /exit. Returns True if command was handled."""
    if user_input == "__CLEAR__":
        conversation.clear_history()
        return True
    if user_input and user_input.strip().lower() == "/clear":
        conversation.clear_history()
        return True
    if user_input and user_input.strip().lower() == "/help":
        if console:
            show_help_message(console)
        return True

    # Show agent tools and external CLI availability
    if user_input and user_input.strip().lower() == "/tools":
        if console:
            if not react_agent:
                console.print("[red]Agent not available[/red]")
                return True
            try:
                st = react_agent.get_status() if hasattr(react_agent, "get_status") else {}
                tools = st.get("tools_available") or list(getattr(react_agent, "tools", {}).keys())
                console.print(f"[cyan]Agent tools[/cyan] ({len(tools)}): {', '.join(sorted(tools)) if tools else 'none'}")
            except Exception as e:
                console.print(f"[yellow]Could not fetch agent tools[/yellow]: {e}")

            # Quick binary availability check for popular CLIs
            try:
                import shutil
                bins = {"rg": "ripgrep", "ast-grep": "ast-grep", "ctags": "universal-ctags"}
                statuses = []
                for b, label in bins.items():
                    ok = shutil.which(b) is not None
                    mark = "[green]✓[/green]" if ok else "[red]✗[/red]"
                    statuses.append(f"{mark} {label}")
                console.print("[dim]CLI availability:[/dim] " + ", ".join(statuses))
            except Exception:
                pass
        return True

    # Handle @ commands for file browsing
    if user_input and user_input.startswith("__AT_COMMAND__"):
        at_command = user_input[14:]  # Remove "__AT_COMMAND__" prefix
        return handle_at_command(at_command, context_manager, path_browser, console)

    # Handle context commands
    if user_input and user_input.strip().lower().startswith("/context"):
        return handle_context_command(user_input.strip(), context_manager, console)

    # Handle RAG commands
    if user_input and user_input.strip().lower().startswith("/rag"):
        return handle_rag_command(user_input.strip(), rag_manager, console)

    # Handle Rails agent commands
    if user_input and user_input.strip().lower().startswith("/agent"):
        return handle_agent_command(user_input.strip(), react_agent, console)

    if user_input is None:
        return True  # Command handled or empty input
    return False


def handle_context_command(user_input: str, context_manager: Optional[ContextManager], console) -> bool:
    """Handle /context commands for file context management.

    Args:
        user_input: The full command input
        context_manager: Context manager instance
        console: Rich console for output

    Returns:
        True if command was handled
    """
    if not context_manager:
        if console:
            console.print("[red]Context manager not available[/red]")
        return True

    # Parse command parts
    parts = user_input.split(None, 2)  # Split into max 3 parts: /context, subcommand, argument

    if len(parts) == 1:
        # Just "/context" - show status
        contexts = context_manager.list_contexts()
        if not contexts:
            console.print("[dim]No active context files[/dim]")
        else:
            console.print(f"[green]Active context: {context_manager.get_status_summary()}[/green]")
            for ctx in contexts:
                console.print(f"  [cyan]{ctx['path']}[/cyan] ({ctx['size']}, added {ctx['timestamp']})")
        return True

    subcommand = parts[1].lower()

    if subcommand == "clear":
        # Clear all context
        context_manager.clear_all_context()
        console.print("[green]All context files cleared[/green]")
        return True

    elif subcommand == "list":
        # List active contexts
        contexts = context_manager.list_contexts()
        if not contexts:
            console.print("[dim]No active context files[/dim]")
        else:
            console.print(f"[green]Active context ({context_manager.get_status_summary()}):[/green]")
            for ctx in contexts:
                console.print(f"  [cyan]{ctx['path']}[/cyan] ({ctx['size']}, added {ctx['timestamp']})")
        return True

    else:
        # Treat as file path (including cases where subcommand is actually a file path)
        file_path = " ".join(parts[1:])  # Rejoin everything after "/context"

        try:
            context_manager.add_file_context(file_path)
            console.print(f"[green]Added context file: {file_path}[/green]")
            console.print(f"[dim]Context status: {context_manager.get_status_summary()}[/dim]")
        except FileNotFoundError:
            console.print(f"[red]File not found: {file_path}[/red]")
        except ValueError as e:
            console.print(f"[red]Error adding context: {e}[/red]")
        except Exception as e:
            console.print(f"[red]Unexpected error: {e}[/red]")

        return True


def handle_at_command(at_command: str, context_manager: Optional[ContextManager], path_browser: Optional[PathBrowser], console) -> bool:
    """Handle @ commands for file browsing and context addition.

    Args:
        at_command: The @ command (e.g., "@", "@/path/", "@file.txt")
        context_manager: Context manager instance
        path_browser: Path browser instance
        console: Rich console for output

    Returns:
        True if command was handled
    """
    if not path_browser:
        if console:
            console.print("[red]Path browser not available[/red]")
        return True

    try:
        # Parse the @ command
        path, is_directory_listing = path_browser.parse_at_command(at_command)

        if is_directory_listing:
            # Suppress printing listings; rely on @ dropdown navigation
            # No output here keeps the input session active and uncluttered.
            return True
        else:
            # File addition to context
            if not context_manager:
                console.print("[red]Context manager not available[/red]")
                return True

            # Validate file first
            is_valid, error_msg = path_browser.validate_file_for_context(path)
            if not is_valid:
                console.print(f"[red]{error_msg}[/red]")
                return True

            # Try to add to context
            try:
                context_manager.add_file_context(path)
                display_path = path_browser.get_relative_path(path)
                console.print(f"[green]Added context file: {display_path}[/green]")
                console.print(f"[dim]Context status: {context_manager.get_status_summary()}[/dim]")
            except ValueError as e:
                console.print(f"[red]Error adding context: {e}[/red]")
            except Exception as e:
                console.print(f"[red]Unexpected error: {e}[/red]")

    except Exception as e:
        console.print(f"[red]Error processing @ command: {e}[/red]")

    return True


def handle_rag_command(user_input: str, rag_manager, console) -> bool:
    """Handle /rag commands.

    Supported:
      /rag index <type> <path>
      /rag search <query> [k]
      /rag on | /rag off
      /rag clear
      /rag status
    """
    if not rag_manager:
        if console:
            console.print("[red]RAG is not available[/red]")
        return True

    parts = user_input.split()
    if len(parts) == 1 or parts[1].lower() == "status":
        st = rag_manager.status()
        console.print(
            f"[cyan]RAG[/cyan]: enabled={st['enabled']} type={st['type']} files={st['files']} chunks={st['chunks']} vocab={st['vocab']} k={st['k']} chunk={st['chunk_size']}/{st['overlap']} char_cap={st['char_cap']} indexed={st['indexed']}"
        )
        return True

    sub = parts[1].lower()
    if sub == "on":
        rag_manager.enabled = True
        console.print("[green]RAG retrieval enabled[/green]")
        return True
    if sub == "off":
        rag_manager.enabled = False
        console.print("[dim]RAG retrieval disabled[/dim]")
        return True
    if sub == "clear":
        rag_manager.clear()
        console.print("[green]RAG index cleared[/green]")
        return True
    if sub == "index":
        if len(parts) < 4:
            console.print("[yellow]Usage: /rag index <type> <path>[/yellow]")
            return True
        idx_type = parts[2]
        path = " ".join(parts[3:])
        try:
            rag_manager.index([path], index_type=idx_type)
            st = rag_manager.status()
            console.print(f"[green]Indexed[/green]: files={st['files']} chunks={st['chunks']} vocab={st['vocab']}")
        except Exception as e:
            console.print(f"[red]Indexing failed[/red]: {e}")
        return True
    if sub == "search":
        if len(parts) < 3:
            console.print("[yellow]Usage: /rag search <query> [k][/yellow]")
            return True
        # Extract k if present (last token numeric)
        k_val = rag_manager.default_k
        try:
            maybe_k = int(parts[-1])
            query = " ".join(parts[2:-1])
            k_val = maybe_k
        except ValueError:
            query = " ".join(parts[2:])
        results = rag_manager.search(query, k=k_val)
        if not results:
            console.print("[dim]No results[/dim]")
            return True
        console.print(f"[cyan]Top {len(results)}[/cyan] for: {query}")
        for i, r in enumerate(results, 1):
            src = f"{r.get('path','')}#{r.get('start',0)}-{r.get('end',0)}"
            preview = (r.get("text") or "").strip().replace("\n", " ")
            if len(preview) > 160:
                preview = preview[:157] + "..."
            console.print(f" {i}. [dim]{src}[/dim]\n    {preview}")
        return True

    console.print("[yellow]Unknown /rag command[/yellow]")
    return True


def handle_agent_command(user_input: str, react_agent, console) -> bool:
    """Handle /agent commands - now deprecated in favor of ride_rails.py."""
    if console:
        console.print("[yellow]/agent commands now live in ride_rails.py[/yellow]")
        console.print("[cyan]For Rails code analysis, use:[/cyan]")
        console.print("[green]  python ride_rails.py --project /path/to/rails/app[/green]")
    return True
