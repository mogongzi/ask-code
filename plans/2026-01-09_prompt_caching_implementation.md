# Prompt Caching Implementation Plan

Implement Cline-style prompt caching for ride_rails using the "last two user messages" strategy.

## Overview

**Goal**: Anthropic/Bedrock prompt caching with cache metrics tracking and cost optimization.

**Key Strategy** (from Cline):
- Mark the **last two user messages** with `cache_control: { type: "ephemeral" }`
- Creates rolling cache breakpoints as conversation grows
- Cache reads cost ~10x less than regular input tokens

## Prompt Cache Constraints (Official Docs)

1. **Maximum 4 cache breakpoints per request**
2. **Caches expire after 5 minutes by default** (ephemeral)
3. **cache_control can ONLY be inserted into text content blocks**
   - Valid: `{"type": "text", "text": "...", "cache_control": {...}}`
   - Invalid on: `tool_result`, `tool_use`, `thinking`, `image` blocks

## ride_rails Message Structure

In ride_rails, "user" role messages come in **two forms**:

```python
# 1. Real user input (HAS text - can add cache_control)
{"role": "user", "content": "Find the SQL source code"}

# 2. Tool results (NO text - cannot add cache_control)
{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "...", "content": "..."}]}
```

**Conversation flow example:**
```
[user: "Find SQL"]              ← Real user (HAS text) ✓
[assistant: text + tool_use]
[user: [tool_result]]           ← Tool result (NO text) ✗
[assistant: text + tool_use]
[user: [tool_result]]           ← Tool result (NO text) ✗
[assistant: "Answer"]
[user: "Follow-up?"]            ← Real user (HAS text) ✓
```

**For caching**: Only count user messages that **contain text content** (skip tool_result-only messages).

## How Prompt Caching Works (Read/Write Breakpoints)

The `cache_control: { type: "ephemeral" }` marker serves as a **cache breakpoint** where the server may:
- **READ** from an existing cache (if prefix matches a cached prefix)
- **WRITE** a new cache (for future requests)

**Why mark the LAST TWO user messages:**
- **2nd-to-last user message** = READ breakpoint (tells server "reuse cache up to here from previous turn")
- **Last user message** = WRITE breakpoint (creates new cache including this for next turn)

Without the 2nd-to-last marker, the server wouldn't know where the previous cache boundary was!

## Optimized Breakpoint Allocation

Since our **system prompt and tools are static** (don't change between requests), they can share ONE cache breakpoint:

| Breakpoint | Location | Purpose |
|------------|----------|---------|
| 1 | Static prefix (system + tools) | Base cache, always reused |
| 2 | 2nd-to-last user message | READ - reuse cache from previous turn |
| 3 | Last user message | WRITE - create cache for next turn |

**Total: 3 breakpoints** (leaves 1 spare under the limit of 4)

**Per-turn behavior (IMPORTANT):**
- Each request: **strip all existing cache_control** from messages first
- Then **add fresh cache_control** to only the last two user messages
- Static prefix cache_control is added by provider (already implemented)

## Rolling Cache Illustration

```
Turn 1 request (only U1 exists):
  [static✓] U1[write✓]
  → Writes cache: static + U1

Turn 2 request (mark U1 + U2):
  [static✓] U1[read✓] A1 U2[write✓]
  → Cache HIT: reads prefix up to U1 (from turn 1 cache)
  → Writes cache: static + U1 + A1 + U2

Turn 3 request (mark U2 + U3):
  [static✓] U1 A1 U2[read✓] A2 U3[write✓]
  → Cache HIT: reads prefix up to U2 (from turn 2 cache)
  → Writes cache: static + ... + U2 + A2 + U3

Turn 4 request (mark U3 + U4):
  [static✓] ... U3[read✓] A3 U4[write✓]
  → Cache HIT: reads prefix up to U3 (from turn 3 cache)
  → Writes cache: static + ... + U3 + A3 + U4
```

**Key insight:** Each turn reuses the cache from the PREVIOUS turn (via the read breakpoint) while creating a NEW cache for the NEXT turn (via the write breakpoint).

## Actual Bedrock API Response Format

Based on real API response:
```json
{
  "usage": {
    "cache_creation": {
      "ephemeral_1h_input_tokens": 0,
      "ephemeral_5m_input_tokens": 0
    },
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 1278,
    "input_tokens": 893,
    "output_tokens": 338
  }
}
```

**Key fields**:
- `input_tokens`: Non-cached input tokens
- `cache_read_input_tokens`: Tokens read from cache (cheap)
- `cache_creation_input_tokens`: Tokens written to cache (expensive)
- `cache_creation.ephemeral_*`: TTL-specific breakdown

---

## Current State (implemented)

- **Static breakpoint**: The last system block carries `cache_control`; if there is no system prompt, the last tool definition is marked instead. This keeps the static prefix to a single breakpoint.
- **Rolling user breakpoints**: `_apply_prompt_caching` marks the last two user messages that have text. Tool-result-only user messages get an empty text block appended so they stay cacheable and keep the rolling two-breakpoint pattern during tool-heavy turns.
- **Provider gating**: `supports_prompt_caching` and `supports_message_cache_control` are enabled for Bedrock and checked before applying markers.
- **Usage & cost**: `BedrockResponseParser.extract_usage` reads cache metrics; `_calculate_cost_with_cache` prices input/output/write/read separately. `LLMResponse` and `UsageInfo` carry cache fields; `UsageTracker` accumulates and displays cache hit ratio and savings.
- **Streaming tokens**: `providers/bedrock.map_events` emits token info including cache metrics; `StreamingClient` parses the extended 6-field format and returns cache token counts.
- **Tests**: `tests/test_prompt_caching.py` covers provider flags, system/tool breakpoint placement, user message marking (including tool_result cases), cache-aware pricing, and tracker display/reset.

## Rationale vs earlier draft

- **Static breakpoint placement**: We keep the breakpoint on the last **system block** (and only fall back to tools when no system). This ensures caching still happens when a system prompt is present even without tools, while using just one static breakpoint.
- **Tool-result messages**: Adding an empty text block to tool-result-only user messages preserves the “last two user messages” rolling pattern in tool-heavy conversations and stays within Anthropic rules (text after tool_result is allowed).

## Remaining gaps

- None identified for Bedrock prompt caching. If Azure/OpenAI later expose equivalent cache semantics, mirror the behavior behind provider capability flags.

## Verification

- Automated: `pytest tests/test_prompt_caching.py -q` (covers caching flags, markers, cost calc, tracker).
- Manual: Run multiple turns with Bedrock provider and confirm `/status` shows cache_read tokens > 0 on subsequent turns and costs drop relative to uncached runs.
