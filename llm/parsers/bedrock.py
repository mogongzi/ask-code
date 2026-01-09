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
        """Extract usage information including cache metrics from Bedrock response.

        Bedrock response format:
        {
            "usage": {
                "input_tokens": 893,          # Non-cached input
                "output_tokens": 338,
                "cache_creation_input_tokens": 0,    # Tokens written to cache
                "cache_read_input_tokens": 1278,     # Tokens read from cache
            }
        }

        Args:
            data: Bedrock response data

        Returns:
            UsageInfo with token counts including cache metrics
        """
        try:
            usage = data.get("usage", {})

            # Bedrock uses mixed casing for usage keys depending on endpoint
            input_tokens = usage.get("input_tokens") or usage.get("inputTokens") or 0
            output_tokens = usage.get("output_tokens") or usage.get("outputTokens") or 0

            # Cache metrics - flat fields in usage
            cache_creation = (
                usage.get("cache_creation_input_tokens") or
                usage.get("cacheCreationInputTokens") or 0
            )
            cache_read = (
                usage.get("cache_read_input_tokens") or
                usage.get("cacheReadInputTokens") or 0
            )

            # Fallback to invocation metrics when present (blocking responses)
            metrics = (
                data.get("amazon-bedrock-invocationMetrics")
                or data.get("amazonBedrockInvocationMetrics")
                or {}
            )
            if metrics:
                input_tokens = metrics.get("inputTokenCount", input_tokens) or input_tokens
                output_tokens = metrics.get("outputTokenCount", output_tokens) or output_tokens
                cache_creation = metrics.get("cacheCreationInputTokenCount", cache_creation) or cache_creation
                cache_read = metrics.get("cacheReadInputTokenCount", cache_read) or cache_read

            # Total tokens = input + output + cached (for context tracking)
            total_tokens = input_tokens + output_tokens + cache_read

            # Calculate cost with cache-specific pricing
            cost = self._calculate_cost_with_cache(
                input_tokens, output_tokens, cache_creation, cache_read
            )

            return UsageInfo(
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                total_tokens=int(total_tokens),
                cost=float(cost),
                cache_creation_input_tokens=int(cache_creation),
                cache_read_input_tokens=int(cache_read)
            )
        except Exception as e:
            logger.error(f"Error extracting usage from Bedrock response: {e}")
            return UsageInfo()

    def _calculate_cost_with_cache(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_creation: int,
        cache_read: int
    ) -> float:
        """Calculate cost with cache-specific pricing.

        Claude 4 Sonnet on Bedrock pricing:
        - Input: $0.003 per 1K tokens ($3/MTok)
        - Output: $0.015 per 1K tokens ($15/MTok)
        - Cache write: $0.00375 per 1K tokens (1.25x input)
        - Cache read: $0.0003 per 1K tokens (0.1x input)
        """
        INPUT_RATE = 0.003
        OUTPUT_RATE = 0.015
        CACHE_WRITE_RATE = 0.00375   # 1.25x input rate
        CACHE_READ_RATE = 0.0003     # 0.1x input rate

        input_cost = (input_tokens / 1000) * INPUT_RATE
        output_cost = (output_tokens / 1000) * OUTPUT_RATE
        cache_write_cost = (cache_creation / 1000) * CACHE_WRITE_RATE
        cache_read_cost = (cache_read / 1000) * CACHE_READ_RATE

        return input_cost + output_cost + cache_write_cost + cache_read_cost
