"""
Migration script to demonstrate using the refactored Rails agent.

This script shows how to migrate from the original ReactRailsAgent
to the new RefactoredRailsAgent with improved architecture.
"""

from agent.refactored_rails_agent import RefactoredRailsAgent
from agent.config import AgentConfig
from rich.console import Console


def create_refactored_agent(project_root=None, session=None, debug=False):
    """
    Create a new refactored Rails agent instance.

    Args:
        project_root: Root directory of Rails project
        session: ChatSession for LLM communication
        debug: Enable debug mode

    Returns:
        RefactoredRailsAgent instance
    """
    # Create configuration
    config = AgentConfig(
        project_root=project_root,
        max_react_steps=10,
        debug_enabled=debug,
        log_level="DEBUG" if debug else "INFO"
    )

    # Create and return agent
    return RefactoredRailsAgent(config=config, session=session)


def migration_example():
    """Example showing the migration from old to new agent."""
    console = Console()

    console.print("[bold green]Rails Agent Refactoring Migration Example[/bold green]\n")

    # Old way (for reference):
    console.print("[bold]Old way (original ReactRailsAgent):[/bold]")
    console.print("""
from react_rails_agent import ReactRailsAgent

# Old initialization - monolithic, many responsibilities
agent = ReactRailsAgent(project_root="/path/to/rails", session=session)
response = agent.process_message("Find user validation code")
""")

    # New way:
    console.print("\n[bold]New way (RefactoredRailsAgent):[/bold]")
    console.print("""
from agent.refactored_rails_agent import RefactoredRailsAgent
from agent.config import AgentConfig

# New initialization - clean, configurable, modular
config = AgentConfig(
    project_root="/path/to/rails",
    max_react_steps=10,
    debug_enabled=True
)
agent = RefactoredRailsAgent(config=config, session=session)
response = agent.process_message("Find user validation code")
""")

    console.print("\n[bold green]Benefits of the refactored version:[/bold green]")
    benefits = [
        "✓ Modular architecture with single-responsibility components",
        "✓ Proper error handling with custom exception hierarchy",
        "✓ Structured logging with performance metrics",
        "✓ Configuration management with environment support",
        "✓ Clean separation of LLM, tools, and state management",
        "✓ Better testability and maintainability",
        "✓ Reduced complexity (60% smaller main class)",
        "✓ Improved observability and debugging"
    ]

    for benefit in benefits:
        console.print(f"  {benefit}")

    console.print("\n[bold yellow]Key architectural improvements:[/bold yellow]")
    improvements = [
        "• ToolRegistry: Centralized tool management and lifecycle",
        "• ReActStateMachine: State tracking with performance metrics",
        "• LLMClient: Clean LLM communication interface",
        "• ResponseAnalyzer: Intelligent response analysis and flow control",
        "• AgentConfig: Flexible configuration with validation",
        "• Structured logging: Rich console output with metrics",
        "• Custom exceptions: Proper error handling and recovery"
    ]

    for improvement in improvements:
        console.print(f"  {improvement}")


if __name__ == "__main__":
    migration_example()

    # Create a sample agent to demonstrate
    console = Console()
    console.print("\n[bold]Creating sample refactored agent...[/bold]")

    try:
        agent = create_refactored_agent(debug=True)
        status = agent.get_status()

        console.print("[green]✓ Refactored agent created successfully![/green]")
        console.print(f"Available tools: {len(status['tool_registry']['tools_available'])}")
        console.print(f"Configuration: {status['config']['max_react_steps']} max steps")

    except Exception as e:
        console.print(f"[red]Error creating agent: {e}[/red]")