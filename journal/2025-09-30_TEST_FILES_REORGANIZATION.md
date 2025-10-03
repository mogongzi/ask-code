# Test Files Reorganization - September 30, 2025

## Overview

Moved all test files from root directory to `tests/` folder and added clear test file policies to project documentation.

## Changes Made

### Files Moved to `tests/`

Four test files were moved from root to `tests/` directory:

1. `test_non_streaming.py` → `tests/test_non_streaming.py`
2. `test_spinner_animation.py` → `tests/test_spinner_animation.py`
3. `test_spinner_styles.py` → `tests/test_spinner_styles.py`
4. `test_transaction_search.py` → `tests/test_transaction_search.py`

### Updated Documentation

Added comprehensive test file policies to both `CLAUDE.md` and `AGENTS.md`:

**CLAUDE.md Updates:**
- Added `tests/` folder to Important section
- Added "Test File Policy" section with naming conventions
- Updated Testing section with clear instructions
- Added examples of correct/incorrect test file placement

**AGENTS.md Updates:**
- Added `tests/` folder to Important section
- Expanded "Testing Guidelines" with detailed organization rules
- Added test framework instructions
- Added test coverage guidelines with examples

## Final Structure

```
ask-code/
├── ride_rails.py
├── streaming_client.py
├── non_streaming_client.py
├── agent_tool_executor.py
│
└── tests/                          # All test files here
    ├── conftest.py                 # Pytest fixtures
    ├── run_tests.py                # Test runner
    │
    ├── test_agent_config.py        # Unit tests
    ├── test_base_tool.py
    ├── test_file_reader_tool.py
    ├── test_infinite_loop_fix.py
    ├── test_insert_search_fix.py
    ├── test_response_analyzer.py
    ├── test_ripgrep_tool.py
    ├── test_state_machine.py
    ├── test_tool_registry.py
    │
    ├── test_non_streaming.py       # Integration tests
    ├── test_spinner_animation.py
    ├── test_spinner_styles.py
    └── test_transaction_search.py
```

## Test File Policy

### Naming Convention
- **Format**: `test_*.py` (must start with `test_` prefix)
- **Location**: `tests/` directory only
- **Examples**:
  - ✅ `tests/test_spinner_animation.py`
  - ✅ `tests/test_non_streaming.py`
  - ❌ `test_my_feature.py` (wrong: in root)
  - ❌ `tests/my_feature_test.py` (wrong: suffix not prefix)

### Test Organization
- **Unit tests**: `tests/test_<module_name>.py`
- **Integration tests**: `tests/test_<feature_name>.py`
- **Test fixtures**: `tests/conftest.py`
- **Test utilities**: `tests/run_tests.py`

### Running Tests
```bash
# All tests
pytest tests/

# Or use test runner
python tests/run_tests.py

# Specific test file
pytest tests/test_spinner_animation.py

# With coverage
pytest tests/ --cov=. --cov-report=html
```

## Benefits

### Organization
- ✅ Clean root directory with no test files
- ✅ All tests in one dedicated location
- ✅ Easy to discover and run tests
- ✅ Clear separation of production and test code

### Maintainability
- ✅ New tests automatically go to correct location
- ✅ Coding agents have explicit instructions
- ✅ Consistent test structure across project

### Developer Experience
- ✅ Simple test discovery: `pytest tests/`
- ✅ Clear test organization by type
- ✅ Centralized test configuration

## Git Changes

```bash
# Files deleted from root (moved to tests/)
D test_non_streaming.py
D test_spinner_animation.py
D test_spinner_styles.py
D test_transaction_search.py

# Files modified
M CLAUDE.md          # Added test file policy
M AGENTS.md          # Added testing guidelines

# New test files in tests/
?? tests/test_non_streaming.py
?? tests/test_spinner_animation.py
?? tests/test_spinner_styles.py
?? tests/test_transaction_search.py
```

## Current Test Inventory

Total: **13 test files** + 2 utilities

**Unit Tests (9 files):**
- `test_agent_config.py` - Agent configuration tests
- `test_base_tool.py` - Base tool class tests
- `test_file_reader_tool.py` - File reader tool tests
- `test_infinite_loop_fix.py` - Loop detection tests
- `test_insert_search_fix.py` - Search functionality tests
- `test_response_analyzer.py` - Response analyzer tests
- `test_ripgrep_tool.py` - Ripgrep tool tests
- `test_state_machine.py` - State machine tests
- `test_tool_registry.py` - Tool registry tests

**Integration Tests (4 files):**
- `test_non_streaming.py` - Non-streaming client tests
- `test_spinner_animation.py` - Spinner animation tests
- `test_spinner_styles.py` - Spinner styles demo
- `test_transaction_search.py` - Transaction search tests

**Test Utilities (2 files):**
- `conftest.py` - Pytest fixtures and configuration
- `run_tests.py` - Test runner script

## Instructions for Future Work

When creating new tests:

1. **Always create in `tests/` directory:**
   ```bash
   # ✅ Correct
   touch tests/test_new_feature.py

   # ❌ Incorrect
   touch test_new_feature.py
   ```

2. **Follow naming convention:**
   - Start with `test_` prefix
   - Use descriptive names
   - Match module or feature name

3. **Use appropriate test type:**
   - Unit test? → `tests/test_<module_name>.py`
   - Integration test? → `tests/test_<feature_name>.py`
   - Shared fixture? → Add to `tests/conftest.py`

4. **Run tests before committing:**
   ```bash
   pytest tests/
   ```

## Related Changes

This reorganization complements the earlier documentation reorganization:
- See `journal/2025-09-30_DOCUMENTATION_REORGANIZATION.md` for journal folder setup
- Both changes contribute to a cleaner, more maintainable project structure

## Conclusion

The project now has a clean, organized test structure with clear policies. All test files are in the dedicated `tests/` directory, and all coding agents are instructed to follow this pattern for future test creation.