# Network Error Highlighting

**Date:** 2025-10-03
**Feature:** Enhanced visibility for network errors
**Status:** ✅ Implemented

## Problem

When the API server or proxy is down, network errors were displayed in regular red text that could be easily missed in the console output, especially when there's a lot of log output from the ReAct agent.

Example of hard-to-see error:
```
Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke
```

## Solution

Network errors are now displayed with high visibility:
- **Bold red text on yellow background** with warning icon (⚠)
- Helpful tip message below the error
- Extra blank lines for visual separation

### Visual Format

```
⚠ Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke
Tip: Check if the API server is running
```

## Implementation

### Files Changed

#### 1. `llm/clients/blocking.py` (Lines 165-174)

**Before:**
```python
# Display error if any
if result.error and console:
    console.print(f"[red]Error: {result.error}[/red]")
```

**After:**
```python
# Display error if any
if result.error and console:
    # Highlight network errors more prominently
    if "Network error" in result.error or "502" in result.error or "Bad Gateway" in result.error:
        console.print()
        console.print(f"[bold red on yellow]⚠ {result.error}[/bold red on yellow]")
        console.print("[yellow]Tip: Check if the API server is running[/yellow]")
        console.print()
    else:
        console.print(f"[red]Error: {result.error}[/red]")
```

#### 2. `agent/logging.py` - Custom Log Handler

Created a custom `RichHandler` that intercepts ALL log messages and highlights network errors.

**New Class (Lines 21-48):**
```python
class NetworkErrorHighlightingHandler(RichHandler):
    """Custom RichHandler that highlights network errors."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record with network error highlighting."""
        message = self.format(record)

        # Check if this is a network error
        is_network_error = (
            "Network error" in message or
            "502" in message or
            "Bad Gateway" in message
        )

        if is_network_error and record.levelno >= logging.ERROR:
            # Print directly with highlighting
            console.print()
            console.print(f"[bold red on yellow]⚠ {message}[/bold red on yellow]")
            console.print("[yellow]Tip: Check if the API server is running[/yellow]")
            console.print()
        else:
            # Use standard RichHandler
            super().emit(record)
```

**Root Logger Configuration (Lines 354-374):**
```python
# Configure root logger to use custom handler for ALL modules
root_logger = logging.getLogger()
handler = NetworkErrorHighlightingHandler(console=console, ...)
root_logger.addHandler(handler)
```

This ensures ALL loggers (including `llm.error_handling`) use the highlighting handler.

**Important:** The StructuredLogger has `propagate = False` set to prevent duplicate logs when both the named logger and root logger have handlers.

## Detection Logic

Network errors are identified by checking for these keywords in the error message:
- `"Network error"` - From `llm/error_handling.py:ErrorHandler.handle_network()`
- `"502"` - HTTP Bad Gateway status code
- `"Bad Gateway"` - HTTP error description

This catches common network failure scenarios:
- API server not running
- Proxy/gateway failures
- Connection refused errors
- Network timeouts

## Testing

Created `tests/test_error_highlighting.py` with:
- ✅ Network error detection tests
- ✅ Regular error exclusion tests
- ✅ Console output format tests

## Usage Example

When the API server is down:

**Before:**
```
⠇ Waiting for response…
Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke
[12:07:56] INFO     [Step 1] Completed operation: llm_call | {"duration_ms": 3157.28}
```

**After:**
```
⠇ Waiting for response…

⚠ Network error: 502 Server Error: Bad Gateway for url: http://127.0.0.1:8000/invoke
Tip: Check if the API server is running

[12:07:56] INFO     [Step 1] Completed operation: llm_call | {"duration_ms": 3157.28}
```

The highlighted error with yellow background is much more visible and immediately tells the user to check the server.

## Key Implementation Note

The logger-based highlighting in `agent/logging.py` is the critical fix, as the screenshot shows errors being logged through the logging system, not displayed via the BlockingClient's console.print path. Both implementations ensure coverage of all error display paths.

## Related Files

- `agent/logging.py` - Logger error highlighting (main fix)
- `llm/clients/blocking.py` - Console error display
- `llm/error_handling.py` - Error message creation
- `tests/test_error_highlighting.py` - Test coverage
