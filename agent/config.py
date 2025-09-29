"""
Configuration management for Rails ReAct agent.

This module provides centralized configuration management with
environment-based overrides and validation.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Set


@dataclass
class AgentConfig:
    """Configuration settings for the Rails ReAct agent."""

    # Core settings
    max_react_steps: int = 10
    project_root: Optional[str] = None

    # Tool configuration
    allowed_tools: Set[str] = field(default_factory=lambda: {
        'ripgrep', 'enhanced_sql_rails_search', 'ast_grep',
        'ctags', 'model_analyzer', 'controller_analyzer', 'route_analyzer',
        'migration_analyzer', 'transaction_analyzer'
    })

    # LLM configuration
    max_tokens: Optional[int] = None
    timeout: float = 30.0

    # Response analysis settings
    finalization_threshold: int = 2  # Steps before forcing finalization
    tool_repetition_limit: int = 3   # Max times same tool can be used

    # Debug and logging
    debug_enabled: bool = field(default=False)
    log_level: str = "INFO"

    def __post_init__(self):
        """Post-initialization validation and environment variable loading."""
        self._load_from_environment()
        self._validate_config()

    def _load_from_environment(self) -> None:
        """Load configuration from environment variables."""
        # Debug settings
        debug_env = os.getenv('AGENT_TOOL_DEBUG', '').lower()
        if debug_env in ('1', 'true', 'yes'):
            self.debug_enabled = True

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

    def _validate_config(self) -> None:
        """Validate configuration values."""
        if self.max_react_steps <= 0:
            raise ValueError("max_react_steps must be positive")

        if self.timeout <= 0:
            raise ValueError("timeout must be positive")

        if self.finalization_threshold <= 0:
            raise ValueError("finalization_threshold must be positive")

        if self.tool_repetition_limit <= 0:
            raise ValueError("tool_repetition_limit must be positive")

        if not self.allowed_tools:
            raise ValueError("allowed_tools cannot be empty")

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
            'allowed_tools': self.allowed_tools.copy(),
            'max_tokens': self.max_tokens,
            'timeout': self.timeout,
            'finalization_threshold': self.finalization_threshold,
            'tool_repetition_limit': self.tool_repetition_limit,
            'debug_enabled': self.debug_enabled,
            'log_level': self.log_level,
        }

        # Update with provided values
        current_values.update(kwargs)

        return AgentConfig(**current_values)

    def to_dict(self) -> dict:
        """Convert configuration to dictionary."""
        return {
            'max_react_steps': self.max_react_steps,
            'project_root': self.project_root,
            'allowed_tools': list(self.allowed_tools),
            'max_tokens': self.max_tokens,
            'timeout': self.timeout,
            'finalization_threshold': self.finalization_threshold,
            'tool_repetition_limit': self.tool_repetition_limit,
            'debug_enabled': self.debug_enabled,
            'log_level': self.log_level,
        }