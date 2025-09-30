#!/usr/bin/env python3
"""
Rails Code Analysis CLI using ReAct Agent

Enhanced Rails code analysis tool that uses the ReAct agent architecture
with improved error handling, configuration, and debugging capabilities.
"""
import argparse
import signal
import os
from typing import List, Optional
from rich.console import Console
from rich.text import Text

# Import core components
from providers import get_provider
from util.command_helpers import handle_special_commands
from util.input_helpers import should_exit_from_input
from chat.session import ChatSession
from streaming_client import StreamingClient
from non_streaming_client import NonStreamingClient

# Import agent components
from agent.react_rails_agent import ReactRailsAgent
from agent.config import AgentConfig
from agent.logging import AgentLogger
from agent_tool_executor import AgentToolExecutor

# Configuration
MAX_TOKEN_SIZE = 20000
DEFAULT_URL = "http://127.0.0.1:8000/invoke"
PROMPT_STYLE = "bold green"
console = Console()
_ABORT = False


def create_streaming_client(use_streaming: bool = False):
    """Create and return streaming or non-streaming client.

    Args:
        use_streaming: If True, use StreamingClient (SSE). If False, use NonStreamingClient (single request).

    Returns:
        StreamingClient or NonStreamingClient instance
    """
    if use_streaming:
        return StreamingClient()
    else:
        return NonStreamingClient()


def get_agent_input(console, prompt_style, display_string, thinking_mode, user_history, tools_enabled):
    """
    Enhanced input function for the Rails agent.

    Includes better error handling and user feedback.
    """
    from util.simple_pt_input import _create_key_bindings, _prompt_for_input

    def _display_enhanced_instructions(token_info: str = None, thinking_mode: bool = False) -> None:
        """Display enhanced usage instructions for the Rails agent."""
        base_instructions = "↵ send    Ctrl+J newline"

        if thinking_mode:
            thinking_part = "/think reasoning [ON]"
        else:
            thinking_part = "/think reasoning"

        instructions = f"{base_instructions}    {thinking_part}    /clear history    /status agent    Esc/Ctrl+C=cancel"

        if token_info:
            terminal_width = 120
            spaces_needed = max(0, terminal_width - len(instructions) - len(f"Tokens: {token_info}"))
            console.print(f"[dim]{instructions}{' ' * spaces_needed}Tokens: {token_info}[/dim]")
        else:
            console.print(f"[dim]{instructions}[/dim]")

    _display_enhanced_instructions(display_string, thinking_mode)
    key_bindings = _create_key_bindings(user_history)

    try:
        user_input = _prompt_for_input(key_bindings, user_history, None)

        if not user_input:
            return None, False, thinking_mode, tools_enabled

        # Handle thinking toggle
        if user_input.strip().lower() == "/think":
            thinking_mode = not thinking_mode
            status = "enabled" if thinking_mode else "disabled"
            console.print(f"[yellow]Reasoning mode {status}[/yellow]")
            return None, True, thinking_mode, tools_enabled

        # Handle clear command
        if user_input.strip().lower() == "/clear":
            return "/clear", False, thinking_mode, tools_enabled

        # Handle status command
        if user_input.strip().lower() == "/status":
            return "/status", False, thinking_mode, tools_enabled

        # Tools are always enabled for Rails analysis
        if user_input.strip().lower() == "/tools":
            console.print("[dim]Tools are always enabled for Rails analysis[/dim]")
            return None, False, thinking_mode, tools_enabled

        return user_input, False, thinking_mode, tools_enabled

    except Exception as e:
        console.print(f"[red]Input error: {e}[/red]")
        return None, False, thinking_mode, tools_enabled


def repl(
    url: str,
    *,
    provider,
    project_root: str,
    debug: bool = False,
    use_streaming: bool = False,
) -> int:
    """
    Enhanced interactive Rails code analysis loop with ReAct agent.

    Args:
        url: LLM endpoint URL
        provider: Provider adapter (bedrock/azure)
        project_root: Rails project root directory
        debug: Enable debug mode
        use_streaming: Use streaming API (SSE) vs non-streaming (single request)

    Returns:
        Exit code (0 for success)
    """
    console.rule("🚀 Enhanced Rails Analysis Agent")

    # Configure logging
    AgentLogger.configure(
        level="DEBUG" if debug else "INFO",
        console=console
    )

    # Validate project root
    if not os.path.exists(project_root):
        console.print(f"[red]Error: Project directory does not exist: {project_root}[/red]")
        return 1

    # Add usage tracking
    from chat.usage_tracker import UsageTracker
    usage = UsageTracker(max_tokens_limit=MAX_TOKEN_SIZE)

    # Extract provider name
    provider_name = provider.__name__.split('.')[-1] if hasattr(provider, '__name__') else "bedrock"

    # Create client (streaming or non-streaming)
    client = create_streaming_client(use_streaming=use_streaming)
    client_type = "streaming (SSE)" if use_streaming else "non-streaming (single request)"
    console.print(f"[dim]Using {client_type} client[/dim]")

    # Create session
    session = ChatSession(
        url=url,
        provider=provider,
        max_tokens=4096,
        timeout=120.0,
        tool_executor=None,
        provider_name=provider_name
    )

    # Add usage tracker and client to session
    session.usage_tracker = usage
    session.streaming_client = client

    # Initialize ReAct agent
    try:
        # Create agent configuration
        config = AgentConfig(
            project_root=project_root,
            max_react_steps=15,  # Generous limit for thorough analysis
            debug_enabled=debug,
            log_level="DEBUG" if debug else "INFO",
            tool_repetition_limit=4,  # Allow some repetition but prevent loops
            finalization_threshold=3   # Request finalization after good results
        )

        react_agent = ReactRailsAgent(config=config, session=session)
        console.print(f"[green]✓ Rails Agent initialized[/green]: {project_root}")

        # Log initialization for debugging
        if debug:
            logger = AgentLogger.get_logger()
            logger.info(f"Created agent for ride_rails.py: {project_root}")
            status = react_agent.get_status()
            logger.debug(f"Agent status: {status}")

        # Show configuration in debug mode
        if debug:
            status = react_agent.get_status()
            config = status['config']
            console.print(f"[dim]Config: {config['max_react_steps']} max steps, "
                         f"debug={config['debug_enabled']}, "
                         f"tools={len(status['tool_registry']['tools_available'])}[/dim]")
    except Exception as e:
        console.print(f"[red]Error: Could not initialize ReAct agent: {e}[/red]")
        if debug:
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1

    # Wire tool executor
    try:
        available_tools = react_agent.tool_registry.get_available_tools()
        agent_executor = AgentToolExecutor(available_tools)
        # Recreate client with tool executor
        if use_streaming:
            session.streaming_client = StreamingClient(tool_executor=agent_executor)
        else:
            session.streaming_client = NonStreamingClient(tool_executor=agent_executor)
        console.print(f"[dim]Tool executor configured with {len(available_tools)} tools[/dim]")

        if debug:
            tool_names = list(available_tools.keys())
            console.print(f"[dim]Available tools: {', '.join(tool_names)}[/dim]")
    except Exception as e:
        console.print(f"[yellow]Warning: could not attach agent tool executor: {e}[/yellow]")

    # Track UI state
    thinking_mode = False
    tools_enabled = True  # Always enabled for Rails agent
    user_history = []

    while True:
        try:
            # Build enhanced display string
            project_name = project_root.split('/')[-1] if project_root else "unknown"
            usage_display = usage.get_display_string()
            mode_indicator = "🧠" if thinking_mode else "🤖"
            display_string = f"{mode_indicator} Rails Analysis • {project_name} • {usage_display}"

            # Get user input
            user_input, use_thinking, thinking_mode, tools_enabled = get_agent_input(
                console,
                PROMPT_STYLE,
                display_string,
                thinking_mode,
                user_history,
                tools_enabled,
            )

            # Handle exit conditions
            if should_exit_from_input(user_input):
                console.print("[dim]Goodbye! 👋[/dim]")
                return 0

            # Handle clear command
            if user_input and user_input.strip().lower() == "/clear":
                user_history.clear()

                if hasattr(session, 'conversation') and session.conversation:
                    session.conversation.clear_history()

                # Clear agent state
                react_agent.state_machine.reset()
                react_agent.conversation_history.clear()

                usage.reset()
                console.print("[green]✓ Conversation and agent state cleared[/green]")
                continue

            # Handle status command
            if user_input and user_input.strip().lower() == "/status":
                status = react_agent.get_status()
                console.print("[bold]Agent Status:[/bold]")
                console.print(f"  Project: {status['config']['project_root']}")
                console.print(f"  Steps completed: {status['state_machine']['current_step']}")
                console.print(f"  Tools used: {len(status['state_machine']['tools_used'])}")
                console.print(f"  Available tools: {len(status['tool_registry']['tools_available'])}")
                console.print(f"  Session queries: {len(user_history)}")
                console.print(f"  Debug mode: {status['config']['debug_enabled']}")
                continue

            # Handle special commands
            if handle_special_commands(user_input, None, console, None, None, None, react_agent):
                continue

        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye! 👋[/dim]")
            return 0
        except Exception as e:
            if debug:
                import traceback
                console.print(f"[red]Unexpected error: {e}[/red]")
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
            else:
                console.print(f"[red]Error: {e}[/red]")
            continue

        # Add to history
        if user_input and isinstance(user_input, str):
            user_history.append(user_input)

        # Process through ReAct agent
        try:
            console.print(f"\n[dim]{mode_indicator} Agent analyzing...[/dim]")

            # Set thinking mode context if enabled
            if thinking_mode:
                AgentLogger.set_context(thinking_mode=True)

            response = react_agent.process_message(user_input)
            console.print()  # Add spacing

            # Show usage and session info
            usage_display = usage.get_display_string()
            session_info = f"Session: {len(user_history)} queries"

            if usage_display:
                console.print(f"[dim]Usage: {usage_display} • {session_info}[/dim]")
            else:
                console.print(f"[dim]{session_info}[/dim]")

            # Show analysis steps summary
            try:
                step_summary = react_agent.get_step_summary(limit=8)
                if step_summary and step_summary.strip() != "No steps recorded.":
                    console.print("[dim]Analysis Steps:[/dim]")
                    for line in step_summary.split('\n'):
                        if line.strip():
                            console.print(f"[dim]  {line}[/dim]")

                # Show detailed status in debug mode
                if debug:
                    status = react_agent.get_status()
                    state = status['state_machine']
                    tools_used = len(state['tools_used'])
                    if tools_used > 0:
                        console.print(f"[dim]Debug: Tools used: {tools_used}, "
                                    f"Step: {state['current_step']}, "
                                    f"Should stop: {state.get('should_stop', False)}[/dim]")
            except Exception as e:
                if debug:
                    console.print(f"[dim]Debug - Step summary error: {e}[/dim]")

        except Exception as e:
            console.print(f"[red]Agent processing error: {e}[/red]")
            if debug:
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")


def main(argv: Optional[List[str]] = None) -> int:
    """Enhanced CLI entry point with better argument parsing."""
    parser = argparse.ArgumentParser(
        prog="ride-rails",
        description="Enhanced Rails Code Analysis Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --project /path/to/rails/app
  %(prog)s --project /path/to/rails/app --debug
  %(prog)s --project /path/to/rails/app --provider azure --debug
        """
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Rails project root directory"
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_URL,
        help=f"Endpoint URL (default: {DEFAULT_URL})"
    )
    parser.add_argument(
        "--provider",
        default="bedrock",
        choices=["bedrock", "azure"],
        help="Provider adapter to use (default: bedrock)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with detailed logging and error traces"
    )
    parser.add_argument(
        "--streaming",
        action="store_true",
        help="Use streaming API (SSE) instead of non-streaming (default: non-streaming)"
    )
    args = parser.parse_args(argv)

    # Setup signal handlers
    def _sigint(_sig, _frm):
        global _ABORT
        _ABORT = True
    def _sigterm(_sig, _frm):
        global _ABORT
        _ABORT = True
    def _sigquit(_sig, _frm):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGINT, _sigint)
        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGQUIT, _sigquit)
    except Exception:
        pass

    # Show startup information
    if args.debug:
        console.print(f"[dim]Debug mode enabled[/dim]")
        console.print(f"[dim]Project: {args.project}[/dim]")
        console.print(f"[dim]Provider: {args.provider}[/dim]")
        console.print(f"[dim]Endpoint: {args.url}[/dim]")

    # Get provider and run REPL
    try:
        provider = get_provider(args.provider)
        code = repl(
            args.url,
            provider=provider,
            project_root=args.project,
            debug=args.debug,
            use_streaming=args.streaming,
        )
        return code
    except Exception as e:
        console.print(f"[red]Startup error: {e}[/red]")
        if args.debug:
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())