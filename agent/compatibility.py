"""
Compatibility layer for transitioning from ReactRailsAgent to RefactoredRailsAgent.

This module provides backward compatibility and migration helpers.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from rich.console import Console

from agent.refactored_rails_agent import RefactoredRailsAgent
from agent.config import AgentConfig


logger = logging.getLogger(__name__)


class ReactRailsAgentCompatibility:
    """
    Compatibility wrapper that provides the old ReactRailsAgent interface
    while using the new RefactoredRailsAgent internally.
    """

    def __init__(self, project_root: Optional[str] = None, session=None):
        """
        Initialize compatibility wrapper.

        Args:
            project_root: Root directory of the Rails project
            session: ChatSession for LLM communication
        """
        # Create default configuration
        config = AgentConfig(
            project_root=project_root,
            max_react_steps=10,  # Match original default
            debug_enabled=False,
            log_level="INFO"
        )

        # Initialize the refactored agent
        self._agent = RefactoredRailsAgent(config=config, session=session)

        # Expose properties for backward compatibility
        self.project_root = project_root
        self.console = Console()
        self.session = session

        # Expose legacy attributes
        self.conversation_history = self._agent.conversation_history
        self.react_steps = []  # Will be populated from state machine

    @property
    def tools(self) -> Dict[str, Any]:
        """Get tools dictionary for backward compatibility."""
        return self._agent.tool_registry.get_available_tools()

    def process_message(self, user_query: str) -> str:
        """
        Process user message using the refactored agent.

        Args:
            user_query: User's natural language query

        Returns:
            Agent's response
        """
        response = self._agent.process_message(user_query)

        # Update legacy react_steps for compatibility
        self._update_legacy_react_steps()

        return response

    def _update_legacy_react_steps(self) -> None:
        """Update legacy react_steps format from state machine."""
        # Convert new format to old format for compatibility
        self.react_steps = []
        for step in self._agent.state_machine.state.steps:
            # Convert to old ReActStep format
            legacy_step = type('ReActStep', (), {
                'step_type': step.step_type.value,
                'content': step.content,
                'tool_name': step.tool_name,
                'tool_input': step.tool_input,
                'tool_output': step.tool_output
            })()
            self.react_steps.append(legacy_step)

    def set_project_root(self, project_root: str) -> None:
        """Update project root (legacy interface)."""
        self.project_root = project_root
        self._agent.set_project_root(project_root)

    def get_status(self) -> Dict[str, Any]:
        """Get agent status (legacy interface)."""
        status = self._agent.get_status()
        # Add legacy fields for compatibility
        status.update({
            "project_root": self.project_root,
            "tools_available": list(self.tools.keys()),
            "conversation_length": len(self.conversation_history),
            "react_steps": len(self.react_steps)
        })
        return status

    def get_step_summary(self, limit: int = 12) -> str:
        """Get step summary (legacy interface)."""
        return self._agent.get_step_summary(limit)


def migrate_from_legacy_agent(legacy_agent, session=None) -> RefactoredRailsAgent:
    """
    Migrate from legacy ReactRailsAgent to RefactoredRailsAgent.

    Args:
        legacy_agent: Original ReactRailsAgent instance
        session: Optional new session

    Returns:
        New RefactoredRailsAgent instance
    """
    # Extract configuration from legacy agent
    project_root = getattr(legacy_agent, 'project_root', None)
    conversation_history = getattr(legacy_agent, 'conversation_history', [])

    # Create new configuration
    config = AgentConfig(
        project_root=project_root,
        max_react_steps=10,
        debug_enabled=False,
        log_level="INFO"
    )

    # Create new agent
    new_agent = RefactoredRailsAgent(
        config=config,
        session=session or getattr(legacy_agent, 'session', None)
    )

    # Migrate conversation history
    new_agent.conversation_history = conversation_history.copy()

    logger.info(f"Migrated legacy agent to refactored version (project: {project_root})")
    return new_agent


def create_agent_for_ask_code(project_root: str, session, debug: bool = False) -> RefactoredRailsAgent:
    """
    Create a properly configured agent for ask_code.py usage.

    Args:
        project_root: Rails project root directory
        session: ChatSession instance
        debug: Enable debug mode

    Returns:
        Configured RefactoredRailsAgent instance
    """
    config = AgentConfig(
        project_root=project_root,
        max_react_steps=15,  # Generous limit for thorough analysis
        debug_enabled=debug,
        log_level="DEBUG" if debug else "INFO",
        tool_repetition_limit=4,  # Allow some repetition but prevent loops
        finalization_threshold=3   # Request finalization after good results
    )

    agent = RefactoredRailsAgent(config=config, session=session)

    # Log initialization for debugging
    if debug:
        logger.info(f"Created agent for ask_code.py: {project_root}")
        status = agent.get_status()
        logger.debug(f"Agent status: {status}")

    return agent