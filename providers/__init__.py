from __future__ import annotations

from importlib import import_module
from typing import Iterator, List, Optional, Tuple


# Unified event type used by provider adapters
Event = Tuple[str, Optional[str]]  # ("model"|"text"|"done"|"tokens", value)


def get_provider(name: str):
    """Dynamically import a provider module by name.

    Valid names include: "bedrock" (Bedrock Anthropic) and "azure" (Azure OpenAI).
    These map directly to modules under `providers.<name>`.
    """
    mod_name = name.strip().lower()
    try:
        return import_module(f"providers.{mod_name}")
    except ImportError as e:
        raise ValueError(f"Unknown provider: {name}") from e


__all__ = ["get_provider", "Event"]
