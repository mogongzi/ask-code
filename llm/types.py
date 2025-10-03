"""
Shared types for LLM client infrastructure.

This module contains type definitions used across all LLM clients,
replacing the old streaming-specific types with generic ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class Provider(Enum):
    """LLM provider types."""
    BEDROCK = "bedrock"
    AZURE = "azure"
    OPENAI = "openai"

    @classmethod
    def from_string(cls, name: str) -> Provider:
        """Convert string to Provider enum, with fallback."""
        name_lower = name.lower()
        for provider in cls:
            if provider.value == name_lower:
                return provider
        # Default to bedrock if unknown
        return cls.BEDROCK


@dataclass
class ToolCall:
    """Represents a single tool call with its execution result.

    Attributes:
        id: Unique identifier for this tool call
        name: Name of the tool being called
        input: Input parameters for the tool (as dict)
        result: Execution result from the tool (empty if not yet executed)
    """
    id: str
    name: str
    input: Dict
    result: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary format for backward compatibility."""
        return {
            "tool_call": {
                "id": self.id,
                "name": self.name,
                "input": self.input
            },
            "result": self.result
        }

    @classmethod
    def from_dict(cls, data: dict) -> ToolCall:
        """Create ToolCall from dictionary format."""
        tool_call = data.get("tool_call", {})
        return cls(
            id=tool_call.get("id", ""),
            name=tool_call.get("name", ""),
            input=tool_call.get("input", {}),
            result=data.get("result", "")
        )


@dataclass
class LLMResponse:
    """Response from an LLM request (streaming or blocking).

    This replaces the old StreamResult class with a more generic name
    that doesn't imply streaming-specific behavior.

    Attributes:
        text: The main text content of the response
        tokens: Total tokens used (input + output)
        cost: Estimated cost in USD
        tool_calls: List of tool calls made during response
        model_name: Name/ID of the model that generated the response
        aborted: Whether the request was aborted by user
        error: Error message if request failed
    """
    text: str
    tokens: int = 0
    cost: float = 0.0
    tool_calls: List[ToolCall] = field(default_factory=list)
    model_name: Optional[str] = None
    aborted: bool = False
    error: Optional[str] = None

    @staticmethod
    def error_response(error_message: str, partial_text: str = "") -> LLMResponse:
        """Factory method for creating error responses.

        Args:
            error_message: The error message
            partial_text: Any partial text that was received before error

        Returns:
            LLMResponse with error set
        """
        return LLMResponse(
            text=partial_text,
            tokens=0,
            cost=0.0,
            tool_calls=[],
            error=error_message
        )

    @staticmethod
    def aborted_response(partial_text: str = "", tool_calls: Optional[List[ToolCall]] = None) -> LLMResponse:
        """Factory method for creating aborted responses.

        Args:
            partial_text: Any partial text that was received before abort
            tool_calls: Any tool calls that were completed before abort

        Returns:
            LLMResponse with aborted flag set
        """
        return LLMResponse(
            text=partial_text,
            tokens=0,
            cost=0.0,
            tool_calls=tool_calls or [],
            aborted=True
        )



@dataclass
class UsageInfo:
    """Token usage and cost information.

    Attributes:
        input_tokens: Number of tokens in the input
        output_tokens: Number of tokens in the output
        total_tokens: Total tokens (input + output)
        cost: Estimated cost in USD
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0

    @classmethod
    def from_totals(cls, total: int, cost: float = 0.0) -> UsageInfo:
        """Create from just total tokens."""
        return cls(
            input_tokens=0,
            output_tokens=0,
            total_tokens=total,
            cost=cost
        )


@dataclass
class StreamEvent:
    """Individual event from an SSE stream.

    Used only by StreamingClient for processing SSE events.

    Attributes:
        kind: Type of event (text, tool_start, tool_ready, etc.)
        value: Optional value associated with the event
    """
    kind: str
    value: Optional[str] = None