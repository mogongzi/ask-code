"""
Rails ReAct Agent package.

This package provides a refactored, clean architecture for the Rails
code analysis agent using the ReAct (Reasoning + Acting) pattern.
"""

from .config import AgentConfig
from .tool_registry import ToolRegistry
from .state_machine import ReActStateMachine, ReActStep, StepType
from .llm_client import LLMClient, LLMResponse
from .response_analyzer import ResponseAnalyzer, AnalysisResult
from .exceptions import (
    AgentError, ToolError, LLMError, ReActError, ConfigurationError,
    ToolInitializationError, ToolExecutionError, ToolNotFoundError,
    LLMCommunicationError, LLMTimeoutError, ReActMaxStepsError,
    ProjectError, ProjectNotFoundError, ProjectNotRailsError
)
from .logging import AgentLogger, StructuredLogger, log_agent_start, log_agent_complete

__all__ = [
    # Configuration
    'AgentConfig',

    # Core components
    'ToolRegistry',
    'ReActStateMachine',
    'LLMClient',
    'ResponseAnalyzer',

    # Data structures
    'ReActStep',
    'StepType',
    'LLMResponse',
    'AnalysisResult',

    # Exceptions
    'AgentError',
    'ToolError',
    'LLMError',
    'ReActError',
    'ConfigurationError',
    'ToolInitializationError',
    'ToolExecutionError',
    'ToolNotFoundError',
    'LLMCommunicationError',
    'LLMTimeoutError',
    'ReActMaxStepsError',
    'ProjectError',
    'ProjectNotFoundError',
    'ProjectNotRailsError',

    # Logging
    'AgentLogger',
    'StructuredLogger',
    'log_agent_start',
    'log_agent_complete',
]

__version__ = '2.0.0'