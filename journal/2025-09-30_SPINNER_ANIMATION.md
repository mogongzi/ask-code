# Spinner Animation for Non-Streaming Mode

## Overview

Added animated spinner to `NonStreamingClient` to provide visual feedback while waiting for LLM API responses.

## Implementation

### Files Modified

1. **`non_streaming_client.py`**:
   - Added `rich.spinner.Spinner` and `rich.live.Live` imports
   - Added `console` parameter to `__init__` method
   - Implemented `_start_spinner()` method to show animated spinner
   - Implemented `_stop_spinner()` method to clean up spinner
   - Updated `send_message()` to show/hide spinner around API call
   - Added spinner cleanup in all error handlers

2. **`ride_rails.py`**:
   - Updated `create_streaming_client()` to accept `console` parameter
   - Pass `console` to `NonStreamingClient` constructor
   - Both client creation points updated (lines 157, 219)

### Features

- **Animated dots spinner** with yellow color
- **Custom message**: "Waiting for response…"
- **Automatic cleanup**: Spinner stops on response or error
- **Graceful fallback**: Falls back to simple text if spinner fails
- **Thread-safe**: Works in both synchronous and async contexts

### Visual Effect

```
⠋ Waiting for response…  ← Animated spinner (rotates during API call)
```

The spinner uses the "dots" style from Rich library, which cycles through:
```
⠋ → ⠙ → ⠹ → ⠸ → ⠼ → ⠴ → ⠦ → ⠧ → ⠇ → ⠏
```

## Usage

### Default (Non-Streaming with Spinner)
```bash
python3 ride_rails.py --project /path/to/rails/project
```

### Streaming Mode (No Spinner, Uses Live Rendering)
```bash
python3 ride_rails.py --project /path/to/rails/project --streaming
```

## Testing

Run the test script to see the spinner in action:
```bash
source .venv/bin/activate
python3 test_spinner_animation.py
```

This simulates a 3-second API delay and shows the animated spinner during the wait.

## Technical Details

### Spinner Lifecycle

1. **Start**: Called at beginning of `send_message()`
2. **Active**: Spinner animates at 10 FPS while waiting
3. **Stop**: Called after receiving response or on error
4. **Cleanup**: `Live` context is properly closed

### Error Handling

All exception handlers call `_stop_spinner()`:
- `ReadTimeout` / `ConnectTimeout`
- `RequestException`
- Generic `Exception`

This ensures the spinner never gets "stuck" on screen.

### Compatibility

- Works with both Bedrock and Azure/OpenAI providers
- Compatible with `stream_with_live_rendering()` method
- Same API as `StreamingClient` for seamless switching

## Benefits

1. **Better UX**: Users know the system is working, not frozen
2. **Professional Look**: Animated feedback is more polished than static text
3. **Reduces Perceived Latency**: Spinner makes wait feel shorter
4. **Clear State**: Obvious when waiting vs when processing response