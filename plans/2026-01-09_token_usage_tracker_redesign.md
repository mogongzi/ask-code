# Plan: Redesign Token Usage Tracker for Claude 4.5 Sonnet with Cache Pricing

## Overview

Update the token usage tracking system to:
1. Use correct Claude 4.5 Sonnet pricing (currently using outdated Claude 3.5 pricing)
2. Handle the new nested `cache_creation` API response format
3. Accurately calculate costs with differentiated cache pricing
4. **New display format** with separate context window and detailed I/O breakdown
5. Fix data-path wiring so granular tokens flow through the entire response chain

## New Display Format

**Current:**
```
Tokens: 71.6k/200k $0.096
```

**New:**
```
Context: 100k/200k Tokens[I/O]:[cache 2.3k/1.5k][1k/0.4k][5.2k] $0.096
```

Breakdown:
- `Context: 100k/200k` - Estimated context for next request (input + cache_read + output + cache_creation)
- `Tokens[I/O]:` - Token breakdown label
- `[cache 2.3k/1.5k]` - Cache tokens (read/write) - **session cumulative**
- `[1k/0.4k]` - Regular tokens (input/output) - **session cumulative**
- `[5.2k]` - Total tokens (all types combined) - **session cumulative**
- `$0.096` - Total cost

## Decisions Made

- **Cache TTL tracking:** Combined total only (sum ephemeral_5m + ephemeral_1h)
- **Context tracking:** Next request estimate (input + cache_read + output + cache_creation from latest request)
- **Tokens[I/O]:** Session cumulative (summed across all API calls)
- **/status cache summary:** Remove it (avoid stale pricing info)

## New Pricing (Claude 4.5 Sonnet on Bedrock)

| Token Type | Rate per 1K tokens |
|------------|-------------------|
| Input | $0.00223 |
| Output | $0.01087 |
| Cache Read | $0.00020 (90% less than input) |
| Cache Write | $0.00254 (25% more than input) |

## Implementation Steps

### Step 1: Fix Data-Path Wiring (HIGH PRIORITY)
**File:** `llm/clients/base.py`

The `BaseLLMClient.send_message()` builds `LLMResponse` but only passes `tokens` and `cost`, not the granular fields. Update lines 118-125:

```python
# Step 4: Build final response
return LLMResponse(
    text=text,
    tokens=usage.total_tokens,
    cost=usage.cost,
    tool_calls=tool_calls,
    model_name=model_name,
    aborted=self._abort,
    # ADD THESE:
    input_tokens=usage.input_tokens,
    output_tokens=usage.output_tokens,
    cache_creation_tokens=usage.cache_creation_input_tokens,
    cache_read_tokens=usage.cache_read_input_tokens
)
```

**File:** `llm/types.py`

Add `input_tokens` and `output_tokens` to `LLMResponse`:
```python
@dataclass
class LLMResponse:
    text: str
    tokens: int = 0
    cost: float = 0.0
    # ... existing fields ...
    input_tokens: int = 0           # ADD
    output_tokens: int = 0          # ADD
    cache_creation_tokens: int = 0  # Already exists
    cache_read_tokens: int = 0      # Already exists
```

### Step 2: Update Pricing Constants
**File:** `llm/parsers/bedrock.py`

Update `_calculate_cost_with_cache()` method:
```python
INPUT_RATE = 0.00223      # $2.23 per 1M tokens
OUTPUT_RATE = 0.01087     # $10.87 per 1M tokens
CACHE_WRITE_RATE = 0.00254  # 25% more than input
CACHE_READ_RATE = 0.00020   # 90% less than input
```

### Step 3: Handle Nested cache_creation Object
**File:** `llm/parsers/bedrock.py`

Update `extract_usage()` to parse the new nested structure with proper fallback:
```python
# Handle nested cache_creation object (new format)
cache_creation_obj = usage.get("cache_creation", {})
ephemeral_5m = cache_creation_obj.get("ephemeral_5m_input_tokens", 0) or 0
ephemeral_1h = cache_creation_obj.get("ephemeral_1h_input_tokens", 0) or 0
nested_sum = ephemeral_5m + ephemeral_1h

# Use nested sum if non-zero, otherwise fall back to flat field
if nested_sum > 0:
    cache_creation = nested_sum
else:
    cache_creation = (
        usage.get("cache_creation_input_tokens") or
        usage.get("cacheCreationInputTokens") or 0
    )
```

### Step 4: Redesign UsageTracker Data Structure
**File:** `chat/usage_tracker.py`

Update `UsageTracker` class to track granular token types:

```python
class UsageTracker:
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
```

Update `update()` method:
```python
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
```

### Step 5: Implement New Display Format
**File:** `chat/usage_tracker.py`

Update `get_display_string()`:
```python
def get_display_string(self) -> Optional[str]:
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

    # Cost part with adaptive precision (preserve existing logic)
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
```

### Step 6: Remove get_cache_summary()
**File:** `chat/usage_tracker.py`

Delete the `get_cache_summary()` method entirely (lines 65-81).

Also update any callers - check `/status` command in `ride_rails.py`.

### Step 7: Update Caller in agent/llm_client.py
**File:** `agent/llm_client.py`

Update lines 150-158 to pass granular token values:
```python
if hasattr(self.session, "usage_tracker") and self.session.usage_tracker:
    if result.tokens > 0 or result.cost > 0:
        self.session.usage_tracker.update(
            input_tokens=getattr(result, 'input_tokens', 0),
            output_tokens=getattr(result, 'output_tokens', 0),
            cache_creation=getattr(result, 'cache_creation_tokens', 0),
            cache_read=getattr(result, 'cache_read_tokens', 0),
            cost=result.cost
        )
```

### Step 8: Update Tests
**File:** `tests/test_prompt_caching.py`

Update `test_cost_calculation_rates()` (lines 128-138) with new pricing:
```python
def test_cost_calculation_rates(self):
    """Verify specific cost calculation rates."""
    parser = BedrockResponseParser()

    # 1000 input tokens at $0.00223/1K = $0.00223
    # 1000 output tokens at $0.01087/1K = $0.01087
    # 1000 cache write tokens at $0.00254/1K = $0.00254
    # 1000 cache read tokens at $0.00020/1K = $0.00020
    cost = parser._calculate_cost_with_cache(1000, 1000, 1000, 1000)
    expected = 0.00223 + 0.01087 + 0.00254 + 0.00020
    assert abs(cost - expected) < 0.0001
```

Also update any tests for `UsageTracker.update()` signature changes.

## Files to Modify

1. `llm/clients/base.py` - Wire granular tokens through LLMResponse
2. `llm/types.py` - Add input_tokens and output_tokens to LLMResponse
3. `llm/parsers/bedrock.py` - Pricing constants and nested object parsing
4. `chat/usage_tracker.py` - New data structure, display format, remove cache_summary
5. `agent/llm_client.py` - Update caller to pass granular token values
6. `ride_rails.py` - Remove /status cache summary display if present
7. `tests/test_prompt_caching.py` - Update pricing tests

## Verification

1. Run tests: `pytest tests/test_prompt_caching.py -v`
2. Run the application with `--verbose` flag
3. Make a few requests and verify:
   - Display shows new format: `Context: Xk/200k Tokens[I/O]:[cache X/X][X/X][X] $X.XXX`
   - Cost calculation is correct for example:
     - input=3, output=248, cache_creation=527, cache_read=14830
     - Expected: (3*0.00223 + 248*0.01087 + 527*0.00254 + 14830*0.00020) / 1000
     - = ~$0.0070
