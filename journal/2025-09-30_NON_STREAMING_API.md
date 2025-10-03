# Non-Streaming API Support

## Overview

The agent now supports both **streaming** (SSE) and **non-streaming** (single request) API modes. Non-streaming mode is the default and provides easier debugging with simpler request/response cycles.

## Usage

### Non-Streaming Mode (Default)

```bash
python3 ride_rails.py --project /path/to/rails/app --debug
```

This uses the `/invoke` endpoint and makes single HTTP POST requests that return complete JSON responses.

### Streaming Mode (Optional)

```bash
python3 ride_rails.py --project /path/to/rails/app --debug --streaming
```

This uses the `/invoke-with-response-stream` endpoint and processes Server-Sent Events (SSE).

## Architecture

### NonStreamingClient

The new `NonStreamingClient` class (`non_streaming_client.py`) provides:

1. **Single HTTP Request**: Makes one POST request and receives complete JSON response
2. **Provider Support**: Handles both Bedrock and Azure/OpenAI response formats
3. **Tool Execution**: Extracts tool calls from response and executes them
4. **Compatible Interface**: Returns `StreamResult` matching `StreamingClient` API

### Response Format Handling

#### Bedrock Format

```json
{
  "output": {
    "message": {
      "content": [
        {"type": "text", "text": "Response text"},
        {"type": "tool_use", "id": "...", "name": "tool_name", "input": {...}}
      ],
      "model": "claude-3-sonnet"
    }
  },
  "usage": {"inputTokens": 100, "outputTokens": 50}
}
```

#### Azure/OpenAI Format

```json
{
  "choices": [{
    "message": {
      "content": "Response text",
      "tool_calls": [
        {
          "id": "call_123",
          "function": {
            "name": "tool_name",
            "arguments": "{...}"
          }
        }
      ]
    }
  }],
  "model": "gpt-4",
  "usage": {"total_tokens": 150}
}
```

## Key Components

### 1. Non-Streaming Client (`non_streaming_client.py`)

```python
class NonStreamingClient:
    def send_message(self, url: str, payload: dict, ...) -> StreamResult:
        # Make single HTTP POST
        response = requests.post(url, json=payload, timeout=timeout)
        data = response.json()

        # Extract content
        text = self._extract_text(data, provider_name)
        model_name = self._extract_model_name(data, provider_name)
        tokens, cost = self._extract_usage(data, provider_name)

        # Execute tools
        tool_calls_made = self._execute_tool_calls(data, provider_name)

        return StreamResult(text, tokens, cost, tool_calls_made, model_name)
```

**Methods**:
- `_extract_text()`: Extract text content based on provider format
- `_extract_model_name()`: Get model name from response
- `_extract_tool_calls()`: Parse tool calls into standardized format
- `_execute_tool_calls()`: Execute tools and collect results
- `_extract_usage()`: Get token usage and cost information

### 2. Client Factory (`ride_rails.py:37-49`)

```python
def create_streaming_client(use_streaming: bool = False):
    """Create streaming or non-streaming client."""
    if use_streaming:
        return StreamingClient()
    else:
        return NonStreamingClient()
```

### 3. CLI Integration (`ride_rails.py`)

Added `--streaming` flag to argparse:

```python
parser.add_argument(
    "--streaming",
    action="store_true",
    help="Use streaming API (SSE) instead of non-streaming (default: non-streaming)"
)
```

## Benefits of Non-Streaming Mode

1. **Simpler Debugging**: Complete request/response visible in logs
2. **No SSE Parsing**: Direct JSON response handling
3. **Easier Testing**: Mock responses are simple JSON objects
4. **Same Functionality**: Tool execution works identically

## Testing

### Unit Tests

Run the non-streaming client test suite:

```bash
python test_non_streaming.py
```

Tests cover:
- Bedrock response format parsing
- Azure/OpenAI response format parsing
- Tool execution with mock executor

### Integration Tests

All existing tests pass with non-streaming client:

```bash
python -m pytest tests/ -q
```

**Result**: 149 tests pass

## Migration Guide

### For Developers

No code changes required! The agent automatically uses non-streaming mode by default.

To explicitly use streaming mode:

```bash
python3 ride_rails.py --project /path/to/rails --debug --streaming
```

### API Endpoint Requirements

| Mode | Endpoint | Response Type |
|------|----------|---------------|
| Non-streaming | `/invoke` | JSON |
| Streaming | `/invoke-with-response-stream` | SSE |

Ensure your LLM endpoint supports the mode you choose.

## Example: Complete Flow

### 1. User Query

```bash
$ python3 ride_rails.py --project /path/to/rails --debug
> Find the Rails code for: SELECT * FROM users WHERE id = 123
```

### 2. NonStreamingClient Request

```json
{
  "messages": [...],
  "tools": [...],
  "max_tokens": 4096
}
```

### 3. LLM Response

```json
{
  "output": {
    "message": {
      "content": [
        {"type": "text", "text": "I'll search for this query."},
        {
          "type": "tool_use",
          "id": "tool_123",
          "name": "enhanced_sql_rails_search",
          "input": {"sql": "SELECT * FROM users WHERE id = 123"}
        }
      ]
    }
  }
}
```

### 4. Tool Execution

NonStreamingClient extracts tool call and executes:

```python
tool_calls = client._extract_tool_calls(data, "bedrock")
# [{"id": "tool_123", "name": "enhanced_sql_rails_search", "input": {...}}]

results = client._execute_tool_calls(data, "bedrock")
# [{"tool_call": {...}, "result": "Found in app/controllers/users_controller.rb:45"}]
```

### 5. Result

```
✓ Using enhanced_sql_rails_search tool...
✓ Found 3 matches in app/controllers/users_controller.rb
```

## Performance Comparison

| Aspect | Streaming | Non-Streaming |
|--------|-----------|---------------|
| Request latency | Low (starts immediately) | Medium (waits for complete response) |
| Debugging | Complex (SSE parsing) | Simple (JSON only) |
| UI responsiveness | High (live updates) | Medium (all at once) |
| Tool execution | During streaming | After response |
| Error handling | Partial results | Complete or nothing |

## Troubleshooting

### "Connection refused" error

Make sure your LLM endpoint is running:

```bash
# Check if endpoint is accessible
curl -X POST http://127.0.0.1:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "test"}]}'
```

### "Invalid JSON" error

Verify the endpoint returns JSON format (not SSE):

```bash
# Should return JSON, not "data: {...}"
curl -X POST http://127.0.0.1:8000/invoke ...
```

If it returns SSE format, use `--streaming` flag.

### Tool not executing

Check tool executor is initialized:

```python
# In ride_rails.py:211-218
agent_executor = AgentToolExecutor(available_tools)
session.streaming_client = NonStreamingClient(tool_executor=agent_executor)
```

## Future Enhancements

- [ ] Cost calculation based on model pricing
- [ ] Streaming simulation for better UX in non-streaming mode
- [ ] Retry logic for failed requests
- [ ] Response caching for repeated queries

## Related Files

- `non_streaming_client.py` - Non-streaming client implementation
- `streaming_client.py` - Original streaming client (still used with `--streaming`)
- `ride_rails.py` - CLI with streaming mode selection
- `test_non_streaming.py` - Test suite for non-streaming client
- `agent/llm_client.py` - High-level LLM client wrapper

## Summary

The non-streaming API support makes debugging easier while maintaining full compatibility with the existing agent architecture. Use `--streaming` flag only when you need real-time streaming updates; otherwise, the default non-streaming mode is simpler and equally functional.