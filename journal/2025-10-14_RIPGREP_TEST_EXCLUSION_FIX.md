# Ripgrep Test Directory Exclusion Fix

**Date:** 2025-10-14
**Component:** `tools/ripgrep_tool.py`
**Issue:** Agent was searching test files when analyzing production SQL logs

## Problem

The agent was returning test files when searching for production code that generated SQL queries:

```ruby
# ❌ WRONG - Agent found test files for production SQL logs
"test/controllers/groups_controller_test.rb" line 747
"test/controllers/groups_controller_test.rb" line 819
```

**Why this is wrong:**
1. Production SQL logs come from **production code**, not test code
2. Test assertions like `assert_redirected_to` don't generate real SQL
3. This wastes search attempts (agent hit 15-step limit)
4. Misleads the agent down the wrong path

## Root Cause

The `ripgrep` tool was searching **all** `.rb` files, including:
- `test/` directory (Minitest)
- `spec/` directory (RSpec)
- `*_test.rb` files
- `*_spec.rb` files

## Solution

Added glob exclusions to ripgrep command to skip test directories:

```python
# Exclude test directories by default (production code search)
cmd.extend([
    "--glob", "!test/**",
    "--glob", "!spec/**",
    "--glob", "!tests/**",
    "--glob", "!*_test.rb",
    "--glob", "!*_spec.rb"
])
```

**Updated tool description:**
```
"Fast text search in Rails codebase using ripgrep. Searches production code only
(excludes test/ spec/ directories). Excellent for finding exact code patterns,
method calls, and string matches."
```

## Impact

### Before Fix
```bash
$ rg 'work_pages.*show_as_tab' --type rb
# Returns:
test/controllers/groups_controller_test.rb:747
test/controllers/groups_controller_test.rb:819
config/routes.rb:923
app/controllers/work_pages_controller.rb:10
```

### After Fix
```bash
$ rg 'work_pages.*show_as_tab' --type rb --glob '!test/**' --glob '!spec/**'
# Returns (production code only):
config/routes.rb:923
app/controllers/work_pages_controller.rb:10
app/controllers/work_pages_controller.rb:602
```

## Benefits

1. **Faster searches**: Skips thousands of test files
2. **More accurate**: Only returns code that actually runs in production
3. **Better agent reasoning**: No confusion between test assertions and real code
4. **Fewer wasted steps**: Agent reaches answer faster

## Testing

Created comprehensive test suite: `tests/test_ripgrep_excludes_tests.py`

```python
def test_ripgrep_excludes_test_directories():
    """Verifies test/, spec/ directories are excluded."""
    # Creates:
    # - app/controllers/users_controller.rb (production)
    # - test/controllers/users_controller_test.rb (should be excluded)
    # - spec/controllers/users_controller_spec.rb (should be excluded)

    # Search for "User.create"
    result = tool.execute({"pattern": "User.create", "file_types": ["rb"]})

    # Verify NO test files in results
    for match in matches:
        assert "test/" not in match["file"]
        assert "spec/" not in match["file"]
        assert not match["file"].endswith("_test.rb")
        assert not match["file"].endswith("_spec.rb")
```

All tests pass: `pytest tests/test_ripgrep_excludes_tests.py -v` ✓

## Edge Cases Handled

1. **Nested test directories**: `test/unit/models/` - excluded
2. **Spec subdirectories**: `spec/requests/api/` - excluded
3. **Test file suffixes**: `user_test.rb`, `user_spec.rb` - excluded
4. **Root tests folder**: `tests/` (alternate naming) - excluded

## Related Issues

This fix addresses the user's observation that:
> "sql from production log cannot be generated from tests"

The agent should never have been searching test files for production SQL analysis.

## Future Considerations

If we ever need to search test files specifically (e.g., for test coverage analysis), we could:
1. Add an optional `include_tests` parameter (default: false)
2. Create a separate `ripgrep_tests` tool
3. Use the `ast_grep` tool which can target specific patterns

For now, the default production-only behavior is correct for 99% of use cases.

## References

- User report: "why agent search test/controllers/groups_controller_test.rb"
- Related fix: `journal/2025-10-14_TRANSACTION_ANALYZER_TOKEN_OPTIMIZATION.md`
