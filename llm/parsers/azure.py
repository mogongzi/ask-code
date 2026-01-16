"""
Azure/OpenAI-specific response parser.

Implements the ResponseParser strategy for Azure OpenAI and OpenAI responses.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from llm.types import UsageInfo

logger = logging.getLogger(__name__)


class AzureResponseParser:
    """Parser for Azure/OpenAI response format.

    Azure/OpenAI response format:
    {
        "choices": [
            {
                "message": {
                    "content": "...",
                    "tool_calls": [
                        {
                            "id": "...",
                            "function": {
                                "name": "...",
                                "arguments": "{...}"  # JSON string
                            }
                        }
                    ]
                }
            }
        ],
        "model": "gpt-4",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
    }
    """

    def extract_text(self, data: dict) -> str:
        """Extract text content from Azure/OpenAI response.

        Args:
            data: Azure/OpenAI response data

        Returns:
            Extracted text or empty string
        """
        try:
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                message = choices[0].get("message", {})
                return message.get("content", "") or ""
            return ""
        except Exception as e:
            logger.error(f"Error extracting text from Azure response: {e}")
            return ""

    def extract_model_name(self, data: dict) -> Optional[str]:
        """Extract model name from Azure/OpenAI response.

        Args:
            data: Azure/OpenAI response data

        Returns:
            Model name or None
        """
        try:
            return data.get("model", None)
        except Exception as e:
            logger.error(f"Error extracting model name from Azure response: {e}")
            return None

    def extract_tool_calls(self, data: dict) -> List[dict]:
        """Extract tool calls from Azure/OpenAI response.

        Args:
            data: Azure/OpenAI response data

        Returns:
            List of standardized tool call dicts
        """
        tool_calls = []

        try:
            choices = data.get("choices", [])
            if choices and isinstance(choices, list):
                message = choices[0].get("message", {})
                raw_tool_calls = message.get("tool_calls", [])

                for tc in raw_tool_calls:
                    if isinstance(tc, dict):
                        function = tc.get("function", {})

                        # Parse function arguments (they come as JSON string)
                        args = function.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse tool arguments: {args}")
                                args = {}

                        tool_calls.append({
                            "id": tc.get("id", ""),
                            "name": function.get("name", ""),
                            "input": args
                        })
        except Exception as e:
            logger.error(f"Error extracting tool calls from Azure response: {e}")

        return tool_calls

    def extract_usage(self, data: dict) -> UsageInfo:
        """Extract usage information from Azure/OpenAI response.

        Args:
            data: Azure/OpenAI response data

        Returns:
            UsageInfo with token counts including cache metrics
        """
        try:
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # Extract cache metrics from prompt_tokens_details
            # Azure/OpenAI returns: {"prompt_tokens_details": {"cached_tokens": N}}
            prompt_details = usage.get("prompt_tokens_details", {})
            cache_read_tokens = prompt_details.get("cached_tokens", 0) if prompt_details else 0

            cost = usage.get("cost")
            if cost is None:
                cost = usage.get("total_cost") or usage.get("usd_cost")

            if cost in (None, 0, 0.0) and (input_tokens or output_tokens):
                # GPT-5 on Azure OpenAI pricing (2025-08-07)
                # Cache read is 90% less than input (same as Claude)
                INPUT_RATE = 0.00091    # $/1K tokens
                OUTPUT_RATE = 0.00677   # $/1K tokens
                CACHE_READ_RATE = 0.00009  # $/1K tokens (90% discount)

                non_cached_input = input_tokens - cache_read_tokens
                input_cost = (non_cached_input / 1000) * INPUT_RATE
                cached_cost = (cache_read_tokens / 1000) * CACHE_READ_RATE
                output_cost = (output_tokens / 1000) * OUTPUT_RATE
                cost = input_cost + cached_cost + output_cost

            return UsageInfo(
                input_tokens=int(input_tokens),
                output_tokens=int(output_tokens),
                total_tokens=int(total_tokens),
                cost=float(cost or 0.0),
                cache_read_input_tokens=int(cache_read_tokens)
            )
        except Exception as e:
            logger.error(f"Error extracting usage from Azure response: {e}")
            return UsageInfo()
