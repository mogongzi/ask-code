"""
LLM client infrastructure.

Provides unified interface for interacting with various LLM providers
using clean architecture principles and design patterns.
"""

from llm.types import (
    Provider,
    ToolCall,
    LLMResponse,
    UsageInfo,
    StreamEvent,
)
from llm.exceptions import (
    LLMError,
    LLMTimeoutError,
    LLMNetworkError,
    LLMResponseError,
    LLMParsingError,
    ToolExecutionError,
    LLMAbortedError,
)
from llm.parsers import (
    ResponseParser,
    BedrockResponseParser,
    AzureResponseParser,
    ParserRegistry,
)

__all__ = [
    # Types
    "Provider",
    "ToolCall",
    "LLMResponse",
    "UsageInfo",
    "StreamEvent",
    # Exceptions
    "LLMError",
    "LLMTimeoutError",
    "LLMNetworkError",
    "LLMResponseError",
    "LLMParsingError",
    "ToolExecutionError",
    "LLMAbortedError",
    # Parsers
    "ResponseParser",
    "BedrockResponseParser",
    "AzureResponseParser",
    "ParserRegistry",
]
