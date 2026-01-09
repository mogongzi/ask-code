"""Token usage and cost tracking with cache metrics."""

from typing import Optional


class UsageTracker:
    """Tracks token usage and costs with granular cache metrics display."""

    def __init__(self, max_tokens_limit: int = 200000):
        # Context window tracking
        self.context_tokens = 0         # Estimated context for next request
        self.max_tokens_limit = max_tokens_limit

        # Granular token tracking (session cumulative)
        self.input_tokens = 0           # Non-cached input tokens
        self.output_tokens = 0          # Output tokens
        self.cache_read_tokens = 0      # Tokens read from cache
        self.cache_creation_tokens = 0  # Tokens written to cache

        # Cost tracking
        self.total_cost = 0.0

    def update(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_creation: int = 0,
        cache_read: int = 0,
        cost: float = 0.0
    ) -> None:
        """Update token and cost counters including cache metrics."""
        # Cumulative token tracking
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cache_creation_tokens += cache_creation
        self.cache_read_tokens += cache_read
        self.total_cost += cost

        # Context = estimate for next request (what was just processed)
        self.context_tokens = input_tokens + cache_read + output_tokens + cache_creation

    def get_display_string(self) -> Optional[str]:
        """Format usage statistics for prompt display.

        Format: Context: Xk/200k Tokens[I/O]:[cache read/write][in/out][total] $X.XXX
        """
        if self.context_tokens <= 0 and self.total_cost <= 0:
            return None

        # Context part: Context: 100k/200k
        context_part = f"Context: {self._format_k(self.context_tokens)}/{self._format_k(self.max_tokens_limit)}"

        # Tokens I/O part: Tokens[I/O]:[cache 2.3k/1.5k][1k/0.4k][5.2k]
        cache_part = f"[cache {self._format_k(self.cache_read_tokens)}/{self._format_k(self.cache_creation_tokens)}]"
        io_part = f"[{self._format_k(self.input_tokens)}/{self._format_k(self.output_tokens)}]"
        total_tokens = self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_creation_tokens
        total_part = f"[{self._format_k(total_tokens)}]"
        tokens_part = f"Tokens[I/O]:{cache_part}{io_part}{total_part}"

        # Cost part with adaptive precision
        if self.total_cost >= 0.01:
            cost_part = f"${self.total_cost:.3f}"
        elif self.total_cost >= 0.001:
            cost_part = f"${self.total_cost:.4f}"
        else:
            cost_part = f"${self.total_cost:.6f}"

        return f"{context_part} {tokens_part} {cost_part}"

    def _format_k(self, value: int) -> str:
        """Format number with k notation."""
        if value >= 1000:
            return f"{value/1000:.1f}k"
        return str(value)

    def reset(self) -> None:
        """Reset all token and cost counters to zero."""
        self.context_tokens = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.cache_read_tokens = 0
        self.cache_creation_tokens = 0
        self.total_cost = 0.0
