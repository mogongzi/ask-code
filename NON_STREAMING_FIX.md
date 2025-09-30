# Non-Streaming API Response Format Fix

## Problem

The NonStreamingClient was not extracting tool calls from the Bedrock API response, causing tools never to execute. The agent showed:

```
WARNING  [Step 1] Agent stuck: 2 consecutive steps without tool calls
```

Even though the LLM was correctly calling the `transaction_analyzer` tool in the API response.

## Root Cause

The NonStreamingClient was using incorrect response parsing logic. It expected nested structure:

```python
# WRONG - Expected format (doesn't match actual response)
content = data.get("output", {}).get("message", {}).get("content", [])
```

But the actual Bedrock `/invoke` endpoint returns a flat structure:

```json
{
  "content": [
    {"type": "text", "text": "..."},
    {"type": "tool_use", "id": "...", "name": "...", "input": {...}}
  ],
  "model": "claude-sonnet-4-20250514",
  "usage": {"input_tokens": 100, "output_tokens": 50}
}
```

## Solution

Updated NonStreamingClient to parse the correct Bedrock response format:

### 1. Text Extraction Fix

**Before**:
```python
content = data.get("output", {}).get("message", {}).get("content", [])
```

**After**:
```python
content = data.get("content", [])  # Direct access, not nested
```

### 2. Tool Call Extraction Fix

**Before**:
```python
content = data.get("output", {}).get("message", {}).get("content", [])
```

**After**:
```python
content = data.get("content", [])  # Direct access
for item in content:
    if item.get("type") == "tool_use":
        # Extract and execute
```

### 3. Model Name Extraction Fix

**Before**:
```python
return data.get("output", {}).get("message", {}).get("model", None)
```

**After**:
```python
return data.get("model", None)  # Top-level field
```

### 4. Usage Extraction Fix

**Before**:
```python
usage.get("inputTokens", 0)  # Wrong case
```

**After**:
```python
usage.get("input_tokens", 0)  # Correct snake_case
```

## Files Modified

1. `non_streaming_client.py:109-134` - Fixed `_extract_text()` for Bedrock format
2. `non_streaming_client.py:136-148` - Fixed `_extract_model_name()` for Bedrock format
3. `non_streaming_client.py:201-252` - Fixed `_extract_tool_calls()` for Bedrock format
4. `non_streaming_client.py:254-282` - Fixed `_extract_usage()` for Bedrock token field names
5. `test_non_streaming.py` - Updated test mocks to match actual Bedrock response format

## Actual Response Format (From Proxy Log)

```json
{
  "content": [
    {
      "text": "I'll analyze this SQL transaction log...",
      "type": "text"
    },
    {
      "id": "toolu_bdrk_014PBfaTipJg7Xif6bpXGFv3",
      "input": {
        "transaction_log": "2025-08-19T08:21:23..."
      },
      "name": "transaction_analyzer",
      "type": "tool_use"
    }
  ],
  "id": "msg_bdrk_01W1KgqnD1stQdkVDFCjAqLG",
  "model": "claude-sonnet-4-20250514",
  "role": "assistant",
  "stop_reason": "tool_use",
  "stop_sequence": null,
  "type": "message",
  "usage": {
    "cache_creation_input_tokens": 0,
    "cache_read_input_tokens": 0,
    "input_tokens": 4810,
    "output_tokens": 1774
  }
}
```

## Testing

### Unit Tests

All tests pass with correct format:

```bash
$ python test_non_streaming.py
✅ ALL TESTS PASSED!
```

### Integration Tests

```bash
$ python -m pytest tests/ -q
149 passed in 0.77s
```

## Expected Behavior After Fix

When running:

```bash
python3 ride_rails.py --project /path/to/rails --debug
```

The agent should now:

1. ✅ Extract text from LLM response
2. ✅ Detect tool calls (e.g., `transaction_analyzer`)
3. ✅ Execute tools with correct parameters
4. ✅ Display tool results
5. ✅ Continue ReAct loop with tool results

Instead of:
- ❌ Agent stuck: 2 consecutive steps without tool calls
- ❌ No tool execution
- ❌ Empty results

## Key Differences: Streaming vs Non-Streaming

| Aspect | Streaming (`/invoke-with-response-stream`) | Non-Streaming (`/invoke`) |
|--------|-------------------------------------------|---------------------------|
| Response Format | SSE (Server-Sent Events) | Single JSON |
| Content Location | `data: {"type":"content_block_delta",...}` | `{"content":[...]}` |
| Tool Detection | Parse SSE events for `tool_use` | Parse JSON `content` array |
| Execution Timing | During streaming | After complete response |
| Field Names | Varies by event type | Consistent JSON structure |

## Verification Steps

To verify the fix works:

1. Start the agent with non-streaming mode (default):
   ```bash
   python3 ride_rails.py --project /path/to/rails --debug
   ```

2. Submit a SQL transaction log query

3. Check debug output for:
   ```
   ⚙ Using transaction_analyzer tool...
   ✓ [tool result output]
   ```

4. Should NOT see:
   ```
   WARNING  [Step 1] Agent stuck: 2 consecutive steps without tool calls
   ```

## Related Documentation

- `NON_STREAMING_API.md` - Full non-streaming API documentation
- `FIXES_SUMMARY.md` - Summary of all bug fixes including non-streaming support
- `non_streaming_client.py` - Implementation
- `test_non_streaming.py` - Test suite