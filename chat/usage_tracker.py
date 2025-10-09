"""Token usage and cost tracking."""

from typing import Optional


class UsageTracker:
    """Tracks token usage and costs with display formatting."""

    def __init__(self, max_tokens_limit: int = 200000):
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.max_tokens_limit = max_tokens_limit

    def update(self, tokens: int, cost: float) -> None:
        """Update token and cost counters."""
        if tokens > 0:
            self.total_tokens_used += tokens
        if cost > 0:
            self.total_cost += cost

    def get_display_string(self) -> Optional[str]:
        """Format usage statistics for prompt display.

        Shows session cumulative tokens vs provider limit without a misleading percent.
        """
        if self.total_tokens_used <= 0:
            return None

        # Format token count with k notation for large numbers (no percentage)
        if self.total_tokens_used >= 1000 or self.max_tokens_limit >= 1000:
            token_part = f"{self.total_tokens_used/1000:.1f}k/{self.max_tokens_limit/1000:.0f}k"
        else:
            token_part = f"{self.total_tokens_used}/{self.max_tokens_limit}"

        # Scale cost precision based on magnitude
        if self.total_cost >= 0.01:
            cost_part = f"${self.total_cost:.3f}"
        elif self.total_cost >= 0.001:
            cost_part = f"${self.total_cost:.4f}"
        else:
            cost_part = f"${self.total_cost:.6f}"

        return f"{token_part} {cost_part}"

    def reset(self) -> None:
        """Reset token and cost counters to zero."""
        self.total_tokens_used = 0
        self.total_cost = 0.0
