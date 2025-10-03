# Refactor: NonStreamingClient → BlockingClient - September 30, 2025

## Overview

Renamed `NonStreamingClient` to `BlockingClient` for better semantic clarity. The old name described what it *wasn't* (non-streaming) rather than what it *is* (blocking/synchronous).

## Rationale

### Problem with Old Name
- ❌ **Negative naming**: "Non-streaming" describes absence, not behavior
- ❌ **Unclear semantics**: Doesn't explain what the client actually does
- ❌ **Poor contrast**: "Streaming vs Non-streaming" is not as clear as "Streaming vs Blocking"

### Benefits of New Name
- ✅ **Positive naming**: "Blocking" describes actual behavior
- ✅ **Standard terminology**: "Blocking" is well-understood in network programming
- ✅ **Clear contrast**: "Streaming vs Blocking" is semantically obvious
- ✅ **Better documentation**: Self-documenting code

## Changes Made

### Files Renamed
- `non_streaming_client.py` → `blocking_client.py`

### Class Renamed
- `NonStreamingClient` → `BlockingClient`

### Updated Files (10 files total)

**Core Code:**
1. `blocking_client.py` - Class name and docstrings
2. `ride_rails.py` - Imports, function names, comments
3. `tests/test_non_streaming.py` - All references
4. `tests/test_spinner_animation.py` - Imports and comments
5. `tests/test_spinner_styles.py` - Documentation references

**Documentation:**
6. `CLAUDE.md` - Core components section, running instructions
7. `AGENTS.md` - Project structure section

### Terminology Changes

| Old Term | New Term | Context |
|----------|----------|---------|
| non-streaming | blocking | Throughout codebase |
| NonStreamingClient | BlockingClient | Class name |
| non_streaming_client | blocking_client | Module name |
| "non-streaming (single request)" | "blocking (single request)" | CLI output |
| "Use streaming API instead of non-streaming" | "Use streaming API instead of blocking" | Help text |

## Code Examples

### Before
```python
from non_streaming_client import NonStreamingClient

client = NonStreamingClient(console=console)
# What does "non-streaming" mean?
```

### After
```python
from blocking_client import BlockingClient

client = BlockingClient(console=console)
# Clear: blocks until response received
```

## Updated Documentation

### CLAUDE.md
```markdown
**Core Components:**
- streaming_client.py: SSE client for streaming responses
- blocking_client.py: Blocking/synchronous client with spinner ✅
```

### AGENTS.md
```markdown
- streaming_client.py manages SSE/stream rendering
- blocking_client.py handles synchronous single-request responses ✅
```

### CLI Help
```bash
--streaming    Use streaming API (SSE) instead of blocking (default: blocking) ✅
```

## Verification

All tests pass with new naming:

```bash
$ python3 -c "from blocking_client import BlockingClient; ..."
✓ BlockingClient imports successfully

$ python3 tests/test_spinner_animation.py
Testing BlockingClient spinner animation...
⠋ Waiting for response…
✓ Spinner test completed!
```

## Git Changes

```bash
# File renamed (preserves history)
R non_streaming_client.py → blocking_client.py

# Modified files
M ride_rails.py
M CLAUDE.md
M AGENTS.md
M tests/test_non_streaming.py
M tests/test_spinner_animation.py
M tests/test_spinner_styles.py
```

## Backward Compatibility

This is a **breaking change** for any external code importing `NonStreamingClient`. However:
- ✅ Internal codebase fully updated
- ✅ All tests updated and passing
- ✅ Documentation updated
- ✅ No external consumers (internal project)

## Related Changes

This refactoring complements earlier improvements:
- See `journal/2025-09-30_SPINNER_ANIMATION.md` for spinner feature
- See `journal/2025-09-30_ANIMATION_SUMMARY.md` for implementation details
- See `journal/2025-09-30_NON_STREAMING_API.md` for API documentation (note: filename unchanged as historical record)

## Benefits

### Code Clarity
- ✅ Self-documenting code
- ✅ Clearer intent for developers
- ✅ Better onboarding experience

### Semantic Accuracy
- ✅ Describes behavior, not absence
- ✅ Standard networking terminology
- ✅ Clear contrast with StreamingClient

### Maintainability
- ✅ Easier to understand codebase
- ✅ Reduced cognitive load
- ✅ Better IDE autocomplete context

## Future Considerations

### Naming Alternatives Considered

1. **BlockingClient** ✅ Chosen
   - Pro: Standard term, clear behavior
   - Pro: Good contrast with StreamingClient

2. **SyncClient**
   - Pro: Short, emphasizes synchronous nature
   - Con: Could be confused with async/sync patterns

3. **RequestClient**
   - Pro: Emphasizes single request
   - Con: Less specific about blocking

4. **SimpleClient**
   - Pro: Emphasizes simplicity
   - Con: "Simple" sounds less capable

### Other Potential Names
- `SingleRequestClient` - Too verbose
- `WaitClient` - Too vague
- `SynchronousClient` - Too long

## Conclusion

The rename from `NonStreamingClient` to `BlockingClient` significantly improves code clarity and semantic accuracy. The name now describes what the client *does* (blocks execution) rather than what it *isn't* (non-streaming), making the codebase more maintainable and easier to understand.