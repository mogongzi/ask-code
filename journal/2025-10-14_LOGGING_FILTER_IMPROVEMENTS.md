# Logging Filter Improvements

**Date**: 2025-10-14
**Issues**:
1. Third-party library DEBUG logs flooding console in verbose mode
2. Duplicate log messages appearing in verbose mode
**Status**: ✅ Fixed

## Problem 1: Third-Party Library Noise

When running with `--verbose` flag, the console was flooded with DEBUG logs from third-party libraries:

- **markdown_it** (from rich/markdown-it-py): "entering paragraph", "entering fence", etc.
- **asyncio**: "Using selector: KqueueSelector"

This made it difficult to see the actual project-specific debug logs that `--verbose` mode is intended to show.

### Root Cause

The `AgentLogger.configure()` method in `agent/logging.py` was setting the **root logger** level to match the requested level (DEBUG in verbose mode). This caused ALL Python loggers, including third-party libraries, to emit DEBUG-level logs.

## Problem 2: Duplicate Log Messages

Some INFO and DEBUG messages were appearing twice in verbose mode:

```
INFO     ReactRailsAgent initialized | {"project_root": "...", ...}
INFO     ReactRailsAgent initialized | {"project_root": "...", ...}
DEBUG    Agent status: {...}
DEBUG    Agent status: {...}
```

### Root Cause

The logging hierarchy had conflicting propagation settings:
1. The `rails_agent` logger (singleton) had its own handler with `propagate=False`
2. Module loggers (`agent.*`, `tools.*`, etc.) were configured to use the root handler
3. When `configure()` was called, it wasn't properly managing handler lifecycle
4. Handlers were either duplicated or propagation was misconfigured

## Solution

Modified `agent/logging.py:343-410` to implement a multi-tier logging strategy:

### 1. Root Logger at WARNING (Always)
```python
root_logger = logging.getLogger()
root_logger.setLevel(logging.WARNING)
```

This prevents third-party libraries from emitting DEBUG logs by default.

### 2. Project Loggers at Requested Level (Without Duplicates)
```python
project_modules = [
    "agent",
    "tools",
    "llm",
    "chat",
    "render",
    "providers",
    "util",
]

for module_name in project_modules:
    module_logger = logging.getLogger(module_name)
    module_logger.setLevel(getattr(logging, level.upper()))
    # Clear any existing handlers to avoid duplicates
    module_logger.handlers.clear()
    # Keep propagate=True so these loggers use the root handler
    module_logger.propagate = True
```

When `--verbose` is used, only project-specific loggers are set to DEBUG level. Module loggers are configured to use the root handler (via propagation) to avoid duplicate output.

### 2.5. Singleton Logger Management
```python
if cls._instance:
    # Update existing instance level without recreating handlers
    cls._instance.logger.setLevel(getattr(logging, level.upper()))
    # Update console if needed without duplicating handlers
    if console:
        cls._instance.console = console
else:
    # Create new instance on first call
    cls._instance = StructuredLogger("rails_agent", level, console)
```

The singleton `rails_agent` logger is carefully managed to avoid recreating handlers on multiple `configure()` calls.

### 3. Explicit Third-Party Silencing
```python
third_party_loggers = [
    "markdown_it",  # markdown-it-py used by rich
    "asyncio",      # asyncio event loop
    "urllib3",      # HTTP library
    "httpx",        # HTTP library
    "httpcore",     # HTTP library
]

for logger_name in third_party_loggers:
    third_party_logger = logging.getLogger(logger_name)
    third_party_logger.setLevel(logging.WARNING)
```

Explicitly sets minimum level for known noisy libraries.

## Behavior

### Without `--verbose` (Default)
- Root logger: WARNING
- Project loggers: WARNING
- Third-party loggers: WARNING
- **Result**: Only WARNING/ERROR messages from all sources

### With `--verbose`
- Root logger: WARNING (prevents third-party DEBUG)
- Project loggers: DEBUG (shows detailed project logs)
- Third-party loggers: WARNING (explicitly filtered)
- **Result**: DEBUG logs from project only, WARNING/ERROR from all sources

## Testing

### Test Suite 1: Logging Filter Tests (`tests/test_logging_filter.py`)

Tests for third-party library filtering:

1. **test_verbose_mode_filters_third_party_logs**: Verifies that verbose mode shows project DEBUG logs but filters third-party DEBUG logs
2. **test_non_verbose_mode_filters_project_debug**: Verifies that non-verbose mode filters project DEBUG logs
3. **test_third_party_warnings_still_appear**: Verifies that third-party WARNING logs still appear (not over-filtered)

### Test Suite 2: Duplicate Logging Tests (`tests/test_duplicate_logs_fixed.py`)

Tests for duplicate message prevention:

1. **test_no_duplicate_logs_from_rails_agent_logger**: Verifies the singleton `rails_agent` logger doesn't log messages twice
2. **test_no_duplicate_logs_from_module_loggers**: Verifies module loggers (`agent.*`, `tools.*`) don't duplicate
3. **test_multiple_configure_calls_dont_duplicate**: Verifies calling `configure()` multiple times doesn't cause duplicates

All tests pass:
```bash
$ pytest tests/test_logging_filter.py tests/test_duplicate_logs_fixed.py -v
============================= test session starts ==============================
tests/test_logging_filter.py::test_verbose_mode_filters_third_party_logs PASSED
tests/test_logging_filter.py::test_non_verbose_mode_filters_project_debug PASSED
tests/test_logging_filter.py::test_third_party_warnings_still_appear PASSED
tests/test_duplicate_logs_fixed.py::test_no_duplicate_logs_from_rails_agent_logger PASSED
tests/test_duplicate_logs_fixed.py::test_no_duplicate_logs_from_module_loggers PASSED
tests/test_duplicate_logs_fixed.py::test_multiple_configure_calls_dont_duplicate PASSED
============================== 6 passed in 0.10s
```

## Files Modified

- `agent/logging.py`: Updated `AgentLogger.configure()` method and singleton management
- `tests/test_logging_filter.py`: New test file for third-party filtering
- `tests/test_duplicate_logs_fixed.py`: New test file for duplicate prevention

## Benefits

1. **Cleaner verbose output**: Only project-specific DEBUG logs appear (no third-party noise)
2. **No duplicate messages**: Each log message appears exactly once
3. **Better debugging**: Can focus on project logs without noise or confusion
4. **Preserved error visibility**: WARNING/ERROR from third-party libraries still appear
5. **Robust configuration**: Multiple `configure()` calls don't break logging
6. **Extensible**: Easy to add more project modules or filter more third-party libraries

## Usage

```bash
# Non-verbose mode (default) - only WARNING and above
python3 ride_rails.py --project /path/to/rails/project

# Verbose mode - DEBUG logs from project only
python3 ride_rails.py --project /path/to/rails/project --verbose
```

## Future Improvements

If more third-party libraries generate noisy logs, simply add them to the `third_party_loggers` list in `agent/logging.py:398-404`.
