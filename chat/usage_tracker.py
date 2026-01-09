"""Token usage and cost tracking with cache metrics."""

from typing import Optional


class UsageTracker:
    """Tracks token usage and costs with cache metrics display."""

    def __init__(self, max_tokens_limit: int = 200000):
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.max_tokens_limit = max_tokens_limit
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0

    def update(
        self,
        tokens: int,
        cost: float,
        cache_creation: int = 0,
        cache_read: int = 0
    ) -> None:
        """Update token and cost counters including cache metrics."""
        if tokens > 0:
            self.total_tokens_used += tokens
        if cost > 0:
            self.total_cost += cost
        if cache_creation > 0:
            self.cache_creation_tokens += cache_creation
        if cache_read > 0:
            self.cache_read_tokens += cache_read

    def get_display_string(self) -> Optional[str]:
        """Format usage statistics for prompt display.

        Shows session cumulative tokens vs provider limit with cache indicator.
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

        # Cache hit indicator
        cache_part = ""
        if self.cache_read_tokens > 0:
            total_cached = self.cache_read_tokens + self.cache_creation_tokens
            if total_cached > 0:
                hit_ratio = self.cache_read_tokens / total_cached * 100
                cache_part = f" [cache {hit_ratio:.0f}%]"

        return f"{token_part} {cost_part}{cache_part}"

    def get_cache_summary(self) -> Optional[str]:
        """Get detailed cache summary for /status command."""
        if self.cache_read_tokens == 0 and self.cache_creation_tokens == 0:
            return None

        parts = []
        if self.cache_creation_tokens > 0:
            parts.append(f"written: {self.cache_creation_tokens/1000:.1f}k")
        if self.cache_read_tokens > 0:
            parts.append(f"read: {self.cache_read_tokens/1000:.1f}k")

        # Estimated savings (cache read at 0.1x vs full input)
        if self.cache_read_tokens > 0:
            savings = (self.cache_read_tokens / 1000) * 0.003 * 0.9  # 90% savings
            parts.append(f"saved: ${savings:.4f}")

        return " | ".join(parts)

    def reset(self) -> None:
        """Reset all token and cost counters to zero."""
        self.total_tokens_used = 0
        self.total_cost = 0.0
        self.cache_creation_tokens = 0
        self.cache_read_tokens = 0
