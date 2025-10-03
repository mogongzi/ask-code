"""
Response parser infrastructure.

Provides Strategy pattern implementation for parsing provider-specific responses.
"""

from llm.parsers.base import ResponseParser
from llm.parsers.bedrock import BedrockResponseParser
from llm.parsers.azure import AzureResponseParser
from llm.parsers.registry import ParserRegistry

__all__ = [
    "ResponseParser",
    "BedrockResponseParser",
    "AzureResponseParser",
    "ParserRegistry",
]
