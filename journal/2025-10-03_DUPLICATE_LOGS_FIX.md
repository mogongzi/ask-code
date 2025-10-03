# Duplicate Logs Fix

**Date:** 2025-10-03
**Issue:** Log messages appearing twice
**Status:** ✅ Fixed

## Problem

After implementing the network error highlighting, log messages were appearing twice:

```
[12:21:41] INFO     Rails ReAct agent started | {"query_length": 97, ...}
[12:21:41] INFO     Rails ReAct agent started | {"query_length": 97, ...}
```

Same message, same timestamp - clearly duplicates.

## Root Cause

**Log Propagation Issue:**

1. `StructuredLogger` creates a named logger (e.g., "rails_agent") with a handler
2. `AgentLogger.configure()` also adds a handler to the root logger
3. Python's logging propagates messages from child loggers to parent loggers
4. Result: Message printed by named logger's handler, then propagates to root logger and prints again

**The flow:**
```
StructuredLogger("rails_agent")
    ↓ (has handler)
logs message
    ↓ (propagate=True by default)
Root Logger
    ↓ (also has handler)
logs same message again = DUPLICATE
```

## Solution

Disable log propagation on the StructuredLogger by setting `propagate = False`.

### Code Change: `agent/logging.py` (Line 82)

**Added:**
```python
# Set up Python logger
self.logger = logging.getLogger(name)
self.logger.setLevel(getattr(logging, level.upper()))

# Disable propagation to avoid duplicate logs when root logger also has handlers
self.logger.propagate = False  # ← NEW LINE

# Clear existing handlers
self.logger.handlers.clear()
```

## Why This Works

- `propagate = False` tells Python's logging system not to pass messages to parent loggers
- The StructuredLogger handles its own messages
- The root logger handles messages from other modules (like `llm.error_handling`)
- No overlap = no duplicates

## Testing

Created `tests/test_duplicate_logs.py` to verify:
- ✅ Log messages appear exactly once
- ✅ Both StructuredLogger and root logger work correctly
- ✅ Network error highlighting still works (via root logger handler)

## Related Files

- `agent/logging.py:82` - Added `propagate = False`
- `tests/test_duplicate_logs.py` - Test coverage
- `journal/2025-10-03_NETWORK_ERROR_HIGHLIGHTING.md` - Related feature
