"""
Tests for agent.config.AgentConfig (simplified version)
"""
import os
import pytest
from unittest.mock import patch

from agent.config import AgentConfig


class TestAgentConfig:
    """Test suite for AgentConfig."""

    def test_default_configuration(self):
        """Test default configuration values."""
        config = AgentConfig()

        assert config.max_react_steps == 20
        assert config.project_root is None
        assert config.debug_enabled is False
        assert config.log_level == "INFO"
        assert config.timeout == 30.0
        assert config.max_exact_repeats == 3  # Simplified: only for exact loops

    def test_custom_configuration(self):
        """Test configuration with custom values."""
        config = AgentConfig(
            max_react_steps=15,
            project_root="/test/project",
            debug_enabled=True,
            log_level="DEBUG",
            timeout=60.0,
            max_exact_repeats=5
        )

        assert config.max_react_steps == 15
        assert config.project_root == "/test/project"
        assert config.debug_enabled is True
        assert config.log_level == "DEBUG"
        assert config.timeout == 60.0
        assert config.max_exact_repeats == 5

    def test_environment_variable_loading(self):
        """Test loading configuration from environment variables."""
        env_vars = {
            'AGENT_LOG_LEVEL': 'WARNING',
            'AGENT_MAX_STEPS': '20',
            'AGENT_TIMEOUT': '45.5'
        }

        with patch.dict(os.environ, env_vars):
            config = AgentConfig()

            assert config.log_level == "WARNING"
            assert config.max_react_steps == 20
            assert config.timeout == 45.5

    def test_invalid_environment_variables_ignored(self):
        """Test that invalid environment variables are ignored."""
        env_vars = {
            'AGENT_LOG_LEVEL': 'INVALID_LEVEL',
            'AGENT_MAX_STEPS': 'not_a_number',
            'AGENT_TIMEOUT': 'invalid_float'
        }

        with patch.dict(os.environ, env_vars):
            config = AgentConfig()

            # Should fallback to defaults
            assert config.log_level == "INFO"
            assert config.max_react_steps == 20
            assert config.timeout == 30.0

    def test_validation_positive_values(self):
        """Test validation of positive values."""
        with pytest.raises(ValueError, match="max_react_steps must be positive"):
            AgentConfig(max_react_steps=0)

        with pytest.raises(ValueError, match="timeout must be positive"):
            AgentConfig(timeout=0)

        with pytest.raises(ValueError, match="max_exact_repeats must be positive"):
            AgentConfig(max_exact_repeats=0)

    def test_create_default(self):
        """Test create_default class method."""
        config = AgentConfig.create_default()

        assert isinstance(config, AgentConfig)
        assert config.max_react_steps == 20
        assert config.debug_enabled is False

    def test_create_for_testing(self):
        """Test create_for_testing class method."""
        config = AgentConfig.create_for_testing()

        assert isinstance(config, AgentConfig)
        assert config.max_react_steps == 5
        assert config.timeout == 10.0
        assert config.debug_enabled is True
        assert config.log_level == "DEBUG"

    def test_update_method(self):
        """Test update method creates new instance with updated values."""
        original = AgentConfig(max_react_steps=10, debug_enabled=False)
        updated = original.update(max_react_steps=15, debug_enabled=True)

        # Original should be unchanged
        assert original.max_react_steps == 10
        assert original.debug_enabled is False

        # Updated should have new values
        assert updated.max_react_steps == 15
        assert updated.debug_enabled is True

        # Other values should be preserved
        assert updated.timeout == original.timeout
        assert updated.log_level == original.log_level

    def test_to_dict(self):
        """Test to_dict method."""
        config = AgentConfig(
            max_react_steps=15,
            project_root="/test",
            debug_enabled=True
        )

        config_dict = config.to_dict()

        assert isinstance(config_dict, dict)
        assert config_dict['max_react_steps'] == 15
        assert config_dict['project_root'] == "/test"
        assert config_dict['debug_enabled'] is True

    def test_log_level_validation(self):
        """Test log level validation through environment variables."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']

        for level in valid_levels:
            with patch.dict(os.environ, {'AGENT_LOG_LEVEL': level}):
                config = AgentConfig()
                assert config.log_level == level
