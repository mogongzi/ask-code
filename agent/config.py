"""
Configuration management for Rails ReAct agent.

This module provides centralized configuration management with
environment-based overrides and validation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AgentConfig:
    """Configuration settings for the Rails ReAct agent."""

    # Core settings
    max_react_steps: int = 20
    project_root: Optional[str] = None

    # LLM configuration
    max_tokens: Optional[int] = None
    timeout: float = 30.0

    # Safety guardrails (only for true infinite loops)
    max_exact_repeats: int = 3  # Only intervene if exact same action repeated 3+ times

    # Debug and logging
    debug_enabled: bool = field(default=False)
    log_level: str = "INFO"

    # Display options
    llm_tracking: bool = False  # Show LLM reasoning trail after final answer

    def __post_init__(self):
        """Post-initialization validation and environment variable loading."""
        self._load_from_environment()
        self._validate_config()

    def _load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        # Logging level
        log_level = os.getenv('AGENT_LOG_LEVEL', '').upper()
        if log_level in ('DEBUG', 'INFO', 'WARNING', 'ERROR'):
            self.log_level = log_level

        # React loop settings
        max_steps = os.getenv('AGENT_MAX_STEPS')
        if max_steps and max_steps.isdigit():
            self.max_react_steps = int(max_steps)

        # Timeout settings
        timeout = os.getenv('AGENT_TIMEOUT')
        if timeout:
            try:
                self.timeout = float(timeout)
            except ValueError:
                pass  # Keep default value

        # LLM tracking setting
        llm_tracking = os.getenv('AGENT_LLM_TRACKING', '').lower()
        if llm_tracking in ('1', 'true', 'yes'):
            self.llm_tracking = True

    def _validate_config(self) -> None:
        """Validate configuration values."""
        if self.max_react_steps <= 0:
            raise ValueError("max_react_steps must be positive")

        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        if self.max_exact_repeats <= 0:
            raise ValueError("max_exact_repeats must be positive")

    @classmethod
    def create_default(cls) -> AgentConfig:
        """Create a default configuration instance."""
        return cls()

    @classmethod
    def create_for_testing(cls) -> AgentConfig:
        """Create a configuration optimized for testing."""
        return cls(
            max_react_steps=5,
            timeout=10.0,
            debug_enabled=True,
            log_level="DEBUG"
        )

    def update(self, **kwargs) -> AgentConfig:
        """
        Create a new config instance with updated values.

        Args:
            **kwargs: Configuration values to update

        Returns:
            New AgentConfig instance with updated values
        """
        # Get current values as dict
        current_values = {
            'max_react_steps': self.max_react_steps,
            'project_root': self.project_root,
            'max_tokens': self.max_tokens,
            'timeout': self.timeout,
            'max_exact_repeats': self.max_exact_repeats,
            'debug_enabled': self.debug_enabled,
            'log_level': self.log_level,
            'llm_tracking': self.llm_tracking,
        }

        # Update with provided values
        current_values.update(kwargs)

        return AgentConfig(**current_values)

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            'max_react_steps': self.max_react_steps,
            'project_root': self.project_root,
            'max_tokens': self.max_tokens,
            'timeout': self.timeout,
            'max_exact_repeats': self.max_exact_repeats,
            'debug_enabled': self.debug_enabled,
            'log_level': self.log_level,
            'llm_tracking': self.llm_tracking,
        }
