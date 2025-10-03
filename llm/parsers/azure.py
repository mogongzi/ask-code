"""
Azure/OpenAI-specific response parser.

Implements the ResponseParser strategy for Azure OpenAI and OpenAI responses.
"""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from llm.types import UsageInfo
from llm.exceptions import LLMParsingError

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
            UsageInfo with token counts
        """
        try:
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

            # TODO: Calculate actual cost based on model pricing
            cost = 0.0

            return UsageInfo(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                cost=cost
            )
        except Exception as e:
            logger.error(f"Error extracting usage from Azure response: {e}")
            return UsageInfo()