"""
Base protocol for LLM response parsers.

Defines the Strategy interface for parsing provider-specific responses.
Each provider implements this protocol with their own parsing logic.
"""

from __future__ import annotations

from typing import Protocol, List, Optional
from llm.types import ToolCall, UsageInfo


class ResponseParser(Protocol):
    """Protocol defining the interface for parsing LLM provider responses.

    This is the Strategy interface - each provider implements these methods
    according to their specific response format.

    All methods should handle errors gracefully and return sensible defaults
    rather than raising exceptions (e.g., empty string, empty list, zero tokens).
    """

    def extract_text(self, data: dict) -> str:
        """Extract the main text content from response data.

        Args:
            data: Raw response data from the provider

        Returns:
            Extracted text content, or empty string if not found
        """
        ...

    def extract_model_name(self, data: dict) -> Optional[str]:
        """Extract the model name/ID from response data.

        Args:
            data: Raw response data from the provider

        Returns:
            Model name if available, None otherwise
        """
        ...

    def extract_tool_calls(self, data: dict) -> List[dict]:
        """Extract tool call definitions from response data.

        Note: This returns raw tool call dicts, not executed results.
        The format is standardized across providers:
        [
            {
                "id": "tool_call_id",
                "name": "tool_name",
                "input": {...}
            },
            ...
        ]

        Args:
            data: Raw response data from the provider

        Returns:
            List of tool call dictionaries, or empty list if none found
        """
        ...

    def extract_usage(self, data: dict) -> UsageInfo:
        """Extract token usage and cost information from response data.

        Args:
            data: Raw response data from the provider

        Returns:
            UsageInfo with token counts and cost, or zeroed values if not found
        """
        ...