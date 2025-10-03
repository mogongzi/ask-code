"""
Bedrock-specific response parser.

Implements the ResponseParser strategy for AWS Bedrock responses.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from llm.types import UsageInfo
from llm.exceptions import LLMParsingError

logger = logging.getLogger(__name__)


class BedrockResponseParser:
    """Parser for AWS Bedrock response format.

    Bedrock response format:
    {
        "content": [
            {"type": "text", "text": "..."},
            {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
        ],
        "model": "claude-3-5-sonnet-20241022",
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50
        }
    }
    """

    def extract_text(self, data: dict) -> str:
        """Extract text content from Bedrock response.

        Args:
            data: Bedrock response data

        Returns:
            Extracted text or empty string
        """
        try:
            content = data.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        return item.get("text", "")
            return ""
        except Exception as e:
            logger.error(f"Error extracting text from Bedrock response: {e}")
            return ""

    def extract_model_name(self, data: dict) -> Optional[str]:
        """Extract model name from Bedrock response.

        Args:
            data: Bedrock response data

        Returns:
            Model name or None
        """
        try:
            return data.get("model", None)
        except Exception as e:
            logger.error(f"Error extracting model name from Bedrock response: {e}")
            return None

    def extract_tool_calls(self, data: dict) -> List[dict]:
        """Extract tool calls from Bedrock response.

        Args:
            data: Bedrock response data

        Returns:
            List of standardized tool call dicts
        """
        tool_calls = []

        try:
            content = data.get("content", [])
            if isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_use":
                        tool_calls.append({
                            "id": item.get("id", ""),
                            "name": item.get("name", ""),
                            "input": item.get("input", {})
                        })
        except Exception as e:
            logger.error(f"Error extracting tool calls from Bedrock response: {e}")

        return tool_calls

    def extract_usage(self, data: dict) -> UsageInfo:
        """Extract usage information from Bedrock response.

        Args:
            data: Bedrock response data

        Returns:
            UsageInfo with token counts
        """
        try:
            usage = data.get("usage", {})
            # Bedrock uses input_tokens and output_tokens (not inputTokens/outputTokens)
            input_tokens = usage.get("input_tokens", 0) or usage.get("inputTokens", 0)
            output_tokens = usage.get("output_tokens", 0) or usage.get("outputTokens", 0)
            total_tokens = input_tokens + output_tokens

            # TODO: Calculate actual cost based on model pricing
            cost = 0.0

            return UsageInfo(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost
            )
        except Exception as e:
            logger.error(f"Error extracting usage from Bedrock response: {e}")
            return UsageInfo()