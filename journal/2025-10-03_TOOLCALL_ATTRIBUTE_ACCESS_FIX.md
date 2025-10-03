# ToolCall Attribute Access Fix

**Date:** 2025-10-03
**Issue:** `'ToolCall' object has no attribute 'get'`
**Status:** ✅ Fixed

## Problem

The Rails analysis agent was crashing with the error:
```
Error calling LLM: 'ToolCall' object has no attribute 'get'
```

This occurred when the agent tried to process tool calls from the LLM response.

## Root Cause

The codebase has two different representations for tool calls:

1. **Old format (dict):** `{"tool_call": {"id": "...", "name": "...", "input": {...}}, "result": "..."}`
2. **New format (dataclass):** `ToolCall` object with attributes `id`, `name`, `input`, `result`

The new `llm.clients` architecture (introduced in the refactoring) uses `ToolCall` dataclass objects in `LLMResponse.tool_calls`. However, some code was still treating these as dictionaries and using `.get()` method.

## Files Fixed

### 1. `agent/llm_client.py` (lines 117-131)

**Before:**
```python
for tool_call in result.tool_calls:
    tool_info = tool_call.get('tool_call', {})
    tool_name = tool_info.get('name', 'unknown')
    # ...
    if tool_call.get('result'):
        result_text = tool_call.get('result', '')
```

**After:**
```python
for tool_call in result.tool_calls:
    # tool_call is a ToolCall object, not a dict
    tool_name = tool_call.name
    # ...
    if tool_call.result:
        result_text = tool_call.result
```

### 2. `agent/react_rails_agent.py` (lines 214-227)

**Before:**
```python
for tool_call in llm_response.tool_calls:
    tool_info = tool_call.get('tool_call', {})
    tool_name = tool_info.get('name', 'unknown')
    tool_input = tool_info.get('input', {})
    # ...
    if tool_call.get('result'):
        result_text = tool_call.get('result', '')
```

**After:**
```python
for tool_call in llm_response.tool_calls:
    # tool_call is a ToolCall object, not a dict
    tool_name = tool_call.name
    tool_input = tool_call.input
    # ...
    if tool_call.result:
        result_text = tool_call.result
```

### 3. `agent/llm_client.py` (lines 232-252) - `format_tool_messages()`

**Before:**
```python
for tool_data in tool_calls_made:
    tc = tool_data.get("tool_call", {})
    tool_use_blocks.append({
        "type": "tool_use",
        "id": tc.get("id"),
        "name": tc.get("name"),
        "input": tc.get("input", {}),
    })
```

**After:**
```python
for tool_call in tool_calls_made:
    # tool_call is a ToolCall object
    tool_use_blocks.append({
        "type": "tool_use",
        "id": tool_call.id,
        "name": tool_call.name,
        "input": tool_call.input,
    })
```

## Summary

Fixed three locations where code was treating `ToolCall` objects as dictionaries:
1. `agent/llm_client.py:117-131` - Processing tool results
2. `agent/react_rails_agent.py:214-227` - Recording actions/observations
3. `agent/llm_client.py:232-252` - Formatting tool messages for conversation

## Architecture Context

The new client architecture (`llm/clients/`) uses this flow:

1. **BaseLLMClient.send_message()** - Template method that:
   - Makes HTTP request (subclass-specific)
   - Parses response using provider-specific parser
   - Extracts and executes tools via `ToolExecutionService`
   - Returns `LLMResponse` with `List[ToolCall]`

2. **ToolExecutionService.extract_and_execute()** - Returns `List[ToolCall]` objects

3. **ToolCall dataclass** - Has methods:
   - `to_dict()` - Convert to old dict format
   - `from_dict()` - Create from old dict format

## Testing

Created `tests/test_toolcall_fix.py` to verify:
- ✅ Direct attribute access works (`tool_call.name`, `tool_call.result`)
- ✅ Dict access fails with `AttributeError` (as expected)
- ✅ Conversion methods `to_dict()` and `from_dict()` work correctly

## Migration Notes

If you're updating code that processes tool calls:

**Don't do this:**
```python
tool_name = tool_call.get('name')  # ❌ ToolCall is not a dict
```

**Do this:**
```python
tool_name = tool_call.name  # ✅ Direct attribute access
```

Or if you need dict format:
```python
tool_dict = tool_call.to_dict()  # ✅ Convert to dict first
tool_name = tool_dict.get('tool_call', {}).get('name')
```

## Related Files

- `llm/types.py` - ToolCall and LLMResponse definitions
- `llm/tool_execution.py` - ToolExecutionService that creates ToolCall objects
- `llm/clients/base.py` - BaseLLMClient template method
- `tests/test_toolcall_fix.py` - Test coverage for this fix
