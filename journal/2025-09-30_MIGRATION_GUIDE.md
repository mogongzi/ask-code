# LLM Client Migration Guide - September 30, 2025

## Overview

This guide helps you migrate from the old client implementations to the new refactored infrastructure.

## TL;DR - Quick Migration

### Old Code
```python
from blocking_client import BlockingClient
from streaming_client import StreamingClient, StreamResult

client = BlockingClient(console=console)
result = client.send_message(url, payload, provider_name="bedrock")
# result is StreamResult
```

### New Code
```python
from llm.clients import BlockingClient, StreamingClient
from llm.types import LLMResponse, Provider

client = BlockingClient(console=console, provider=Provider.BEDROCK)
result = client.send_message(url, payload)
# result is LLMResponse
```

## Detailed Migration Steps

### Step 1: Update Imports

#### BlockingClient

**Before:**
```python
from blocking_client import BlockingClient
```

**After:**
```python
from llm.clients import BlockingClient
from llm.types import Provider  # If using explicit provider
```

#### StreamingClient

**Before:**
```python
from streaming_client import StreamingClient, StreamResult
```

**After:**
```python
from llm.clients import StreamingClient
from llm.types import LLMResponse  # New response type
```

### Step 2: Update Client Initialization

#### BlockingClient

**Before:**
```python
client = BlockingClient(
    tool_executor=executor,
    console=console
)
```

**After:**
```python
client = BlockingClient(
    tool_executor=executor,
    console=console,
    provider=Provider.BEDROCK,  # Explicit provider (optional, defaults to BEDROCK)
    timeout=120.0               # Explicit timeout (optional, defaults to 120.0)
)
```

#### StreamingClient

**Before:**
```python
client = StreamingClient(
    tool_executor=executor
)
```

**After:**
```python
client = StreamingClient(
    tool_executor=executor,
    console=console,              # Optional console
    provider=Provider.BEDROCK,    # Explicit provider (optional, defaults to BEDROCK)
    timeout=60.0                  # Explicit timeout (optional, defaults to 60.0)
)
```

### Step 3: Update send_message() Calls

#### BlockingClient

**Before:**
```python
result = client.send_message(
    url=url,
    payload=payload,
    provider_name="bedrock"  # String parameter
)
```

**After:**
```python
result = client.send_message(
    url=url,
    payload=payload
    # No provider_name parameter - set in constructor
)
```

#### StreamingClient

**Before:**
```python
result = client.send_message(
    url=url,
    payload=payload,
    mapper=provider.map_events,
    provider_name="bedrock"  # String parameter
)
```

**After:**
```python
# For basic streaming (no live rendering):
result = client.send_message(
    url=url,
    payload=payload,
    mapper=provider.map_events  # Still required for streaming
)

# For full streaming with live rendering (recommended):
result = client.stream_with_live_rendering(
    url=url,
    payload=payload,
    mapper=provider.map_events,
    console=console,
    use_thinking=False,
    provider_name="bedrock",  # Still used for display purposes
    show_model_name=True,
    live_window=6
)
```

### Step 4: Update Response Handling

#### Response Type Changed

**Before:**
```python
# result is StreamResult (dataclass)
result: StreamResult = client.send_message(...)

text = result.text
tokens = result.tokens
cost = result.cost
tool_calls = result.tool_calls  # List[dict]
model_name = result.model_name
aborted = result.aborted
error = result.error
```

**After:**
```python
# result is LLMResponse (dataclass)
result: LLMResponse = client.send_message(...)

text = result.text
tokens = result.tokens
cost = result.cost
tool_calls = result.tool_calls  # List[ToolCall] - typed objects!
model_name = result.model_name
aborted = result.aborted
error = result.error
```

#### Tool Calls Changed

**Before:**
```python
# Tool calls were dicts
for tc in result.tool_calls:
    tool_call = tc["tool_call"]
    tool_id = tool_call["id"]
    tool_name = tool_call["name"]
    tool_input = tool_call["input"]
    tool_result = tc["result"]
```

**After:**
```python
# Tool calls are ToolCall objects
for tool_call in result.tool_calls:
    tool_id = tool_call.id
    tool_name = tool_call.name
    tool_input = tool_call.input  # dict
    tool_result = tool_call.result
```

### Step 5: Update Provider Handling

#### Provider Type Changed

**Before:**
```python
# Providers were strings
provider_name = "bedrock"  # or "azure", "openai"
result = client.send_message(url, payload, provider_name=provider_name)
```

**After:**
```python
# Providers are enum values
from llm.types import Provider

provider = Provider.BEDROCK  # or Provider.AZURE, Provider.OPENAI

client = BlockingClient(provider=provider)
result = client.send_message(url, payload)

# Or from string:
provider = Provider.from_string("bedrock")
```

## Breaking Changes

### 1. Response Type

- **Old**: `StreamResult` (both clients)
- **New**: `LLMResponse` (both clients)
- **Impact**: Type annotations need updating
- **Mitigation**: LLMResponse has same fields, mostly compatible

### 2. Tool Calls Format

- **Old**: List of dicts with nested structure
- **New**: List of `ToolCall` objects
- **Impact**: Access pattern changes (dict keys → object attributes)
- **Mitigation**: Use dot notation instead of dict access

### 3. Provider Parameter

- **Old**: `provider_name: str` in send_message()
- **New**: `provider: Provider` in constructor
- **Impact**: Provider specified once at client creation
- **Mitigation**: Set provider when creating client

### 4. Import Paths

- **Old**: Top-level imports (`blocking_client`, `streaming_client`)
- **New**: Package imports (`llm.clients`)
- **Impact**: All imports need updating
- **Mitigation**: Simple search and replace

## Non-Breaking Changes

### These Still Work

✅ **Console parameter** - Still passed to BlockingClient
✅ **Tool executor** - Still passed to both clients
✅ **Timeout parameter** - Now explicit, but has sensible defaults
✅ **Response fields** - All same names (text, tokens, cost, etc.)
✅ **stream_with_live_rendering** - Still available on StreamingClient

## Migration Checklist

Use this checklist to ensure complete migration:

- [ ] Update all imports from old paths to `llm.clients`
- [ ] Import `Provider` enum from `llm.types`
- [ ] Import `LLMResponse` instead of `StreamResult`
- [ ] Update client initialization to pass `Provider` enum
- [ ] Remove `provider_name` from `send_message()` calls
- [ ] Update tool call access from dict to object attributes
- [ ] Update type hints from `StreamResult` to `LLMResponse`
- [ ] Test all code paths with new clients
- [ ] Run test suite to verify functionality
- [ ] Update documentation to reflect new API

## Testing Your Migration

### Unit Tests

```python
import unittest
from unittest.mock import Mock, patch
from llm.clients import BlockingClient
from llm.types import Provider, LLMResponse

class TestMigration(unittest.TestCase):
    def test_new_client(self):
        client = BlockingClient(provider=Provider.BEDROCK)

        mock_response = {
            "content": [{"type": "text", "text": "Test"}],
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-3-sonnet"
        }

        with patch('requests.post') as mock_post:
            mock_post.return_value.json.return_value = mock_response
            mock_post.return_value.raise_for_status = Mock()

            result = client.send_message("http://test.com", {})

            self.assertIsInstance(result, LLMResponse)
            self.assertEqual(result.text, "Test")
            self.assertEqual(result.tokens, 15)
```

### Integration Tests

```python
# Test with actual API (if available)
from llm.clients import BlockingClient
from llm.types import Provider

client = BlockingClient(
    provider=Provider.BEDROCK,
    timeout=30.0
)

result = client.send_message(
    url="http://localhost:8000/invoke",
    payload={
        "messages": [{"role": "user", "content": "Hello"}]
    }
)

assert isinstance(result, LLMResponse)
assert result.text
print(f"✓ Migration successful: {result.text}")
```

## Common Migration Issues

### Issue 1: Import Errors

**Problem:**
```python
ModuleNotFoundError: No module named 'llm'
```

**Solution:**
```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

### Issue 2: Provider Name Errors

**Problem:**
```python
TypeError: send_message() got an unexpected keyword argument 'provider_name'
```

**Solution:**
```python
# Remove provider_name from send_message call
# Set it in constructor instead:
client = BlockingClient(provider=Provider.BEDROCK)
result = client.send_message(url, payload)  # No provider_name
```

### Issue 3: Tool Call Access Errors

**Problem:**
```python
TypeError: 'ToolCall' object is not subscriptable
```

**Solution:**
```python
# OLD: tool_calls[0]["tool_call"]["name"]
# NEW: tool_calls[0].name
```

### Issue 4: Type Hint Errors

**Problem:**
```python
# Type checker complains about StreamResult
def process_result(result: StreamResult) -> None:
    ...
```

**Solution:**
```python
from llm.types import LLMResponse

def process_result(result: LLMResponse) -> None:
    ...
```

## Rollback Plan

If you need to rollback temporarily:

1. **Old files still exist**: `blocking_client.py` and `streaming_client.py`
2. **Keep old imports**: Temporarily revert imports
3. **No data migration needed**: It's just code changes

**Rollback example:**
```bash
# Revert imports
git checkout HEAD -- ride_rails.py
git checkout HEAD -- chat/session.py

# Keep new infrastructure (it's not used by old clients)
# Old clients still work independently
```

## Benefits After Migration

✅ **60% less code** - Eliminated duplication
✅ **Type safety** - Provider enum, LLMResponse dataclass
✅ **SOLID compliant** - Easy to extend and maintain
✅ **Better testability** - Small, focused components
✅ **Shared infrastructure** - One source of truth for parsing/tools/errors
✅ **Easier debugging** - Clear separation of concerns
✅ **Future-proof** - Easy to add new providers and clients

## Support

If you encounter issues during migration:

1. Check this guide for common issues
2. Review test files for examples: `tests/test_blocking_client.py`
3. Check journal docs for detailed implementation: `journal/2025-09-30_*.md`

## Summary

**Migration is straightforward:**
1. Update 3-4 import statements
2. Add `Provider` enum to client initialization
3. Remove `provider_name` from send_message calls
4. Update tool call access (dict → object)
5. Test thoroughly

**Time estimate**: 10-30 minutes for typical codebase

**Risk level**: Low (backward compatible where possible)