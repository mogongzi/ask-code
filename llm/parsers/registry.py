"""
Parser registry and factory.

Implements the Factory pattern for creating provider-specific parsers.
"""

from __future__ import annotations

import logging
from typing import Dict, Type

from llm.types import Provider
from llm.parsers.base import ResponseParser
from llm.parsers.bedrock import BedrockResponseParser
from llm.parsers.azure import AzureResponseParser

logger = logging.getLogger(__name__)


class ParserRegistry:
    """Registry for provider-specific response parsers.

    Implements the Factory pattern - creates appropriate parser based on provider type.
    This follows the Open/Closed Principle: adding new providers doesn't require
    modifying existing code, just registering a new parser.
    """

    _parsers: Dict[Provider, Type[ResponseParser]] = {
        Provider.BEDROCK: BedrockResponseParser,
        Provider.AZURE: AzureResponseParser,
        Provider.OPENAI: AzureResponseParser,  # OpenAI uses same format as Azure
    }

    _instances: Dict[Provider, ResponseParser] = {}

    @classmethod
    def register(cls, provider: Provider, parser_class: Type[ResponseParser]) -> None:
        """Register a new parser for a provider.

        This allows extending the system with new providers without modifying existing code.

        Args:
            provider: The provider enum value
            parser_class: The parser class to use for this provider

        Example:
            >>> class CustomParser(ResponseParser):
            ...     # implementation
            >>> ParserRegistry.register(Provider.CUSTOM, CustomParser)
        """
        cls._parsers[provider] = parser_class
        # Clear cached instance if it exists
        if provider in cls._instances:
            del cls._instances[provider]

        logger.info(f"Registered parser {parser_class.__name__} for provider {provider.value}")

    @classmethod
    def get_parser(cls, provider: Provider) -> ResponseParser:
        """Get parser instance for the given provider.

        Uses singleton pattern - each provider gets one parser instance that's reused.

        Args:
            provider: The provider to get parser for

        Returns:
            ResponseParser instance for the provider

        Raises:
            ValueError: If provider not registered
        """
        # Return cached instance if available
        if provider in cls._instances:
            return cls._instances[provider]

        # Get parser class
        parser_class = cls._parsers.get(provider)
        if not parser_class:
            raise ValueError(
                f"No parser registered for provider {provider.value}. "
                f"Available providers: {[p.value for p in cls._parsers.keys()]}"
            )

        # Create and cache instance
        parser = parser_class()
        cls._instances[provider] = parser

        logger.debug(f"Created parser instance for provider {provider.value}")
        return parser

    @classmethod
    def get_parser_by_name(cls, provider_name: str) -> ResponseParser:
        """Get parser by provider name string.

        Convenience method that converts string to Provider enum first.

        Args:
            provider_name: Provider name as string (case-insensitive)

        Returns:
            ResponseParser instance for the provider

        Example:
            >>> parser = ParserRegistry.get_parser_by_name("bedrock")
            >>> parser = ParserRegistry.get_parser_by_name("AZURE")
        """
        provider = Provider.from_string(provider_name)
        return cls.get_parser(provider)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names.

        Returns:
            List of provider names
        """
        return [p.value for p in cls._parsers.keys()]