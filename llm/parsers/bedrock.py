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

            # Bedrock uses mixed casing for usage keys depending on endpoint
            input_tokens = usage.get("input_tokens") or usage.get("inputTokens") or 0
            output_tokens = usage.get("output_tokens") or usage.get("outputTokens") or 0
            total_tokens = usage.get("total_tokens") or usage.get("totalTokens") or (input_tokens + output_tokens)

            # Fallback to invocation metrics when present (blocking responses)
            metrics = (
                data.get("amazon-bedrock-invocationMetrics")
                or data.get("amazonBedrockInvocationMetrics")
                or {}
            )
            if metrics:
                input_tokens = metrics.get("inputTokenCount", input_tokens) or input_tokens
                output_tokens = metrics.get("outputTokenCount", output_tokens) or output_tokens
                total_tokens = metrics.get("totalTokenCount", total_tokens) or total_tokens

            cost = usage.get("cost")
            if cost is None:
                cost = usage.get("total_cost") or usage.get("usd_cost")

            if cost in (None, 0, 0.0) and (input_tokens or output_tokens):
                # Estimate cost using Claude 3.5 Sonnet pricing as default
                input_cost = (input_tokens / 1000) * 0.00204
                output_cost = (output_tokens / 1000) * 0.00988
                cost = input_cost + output_cost

            return UsageInfo(
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                total_tokens=int(total_tokens),
                cost=float(cost or 0.0)
            )
        except Exception as e:
            logger.error(f"Error extracting usage from Bedrock response: {e}")
            return UsageInfo()
