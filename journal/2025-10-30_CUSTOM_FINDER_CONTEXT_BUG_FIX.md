# Custom Finder Auto-Detection Context Bug Fix

**Date:** 2025-10-30
**Status:** ✓ Fixed and Verified
**Files Modified:** `tools/components/where_clause_matcher.py`

## Problem

The custom finder auto-detection worked correctly in isolation but failed when the code snippet had surrounding context with multiple method calls.

### Failing Test Case

**Code:** `alert_mailer.rb:180`
```ruby
else
  active_members = VirtualCollection.new(page_size) do |page|
    company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)
  end
end
```

**Expected Behavior:**
1. Detect `company.find_all_active` as a custom finder
2. Read method definition from `Company#find_all_active` → `members.active`
3. Expand to: `company.members.active.offset(...).limit(...).order(...)`
4. Extract 5 WHERE conditions:
   - `company_id = ?`
   - `disabler_id IS NULL`
   - `owner_id IS NULL`
   - `login_handle IS NOT NULL`
   - `first_login_at IS NOT NULL`

**Actual Behavior (before fix):**
- Only 1 condition extracted: `VirtualCollection_id = None`
- Parser was finding `VirtualCollection.new` first instead of `company.find_all_active`

## Root Cause

The bug was in the code expansion logic (`parse_ruby_code` method, lines 590-636):

1. `_parse_custom_finder_method()` correctly iterated through ALL method calls (lines 454-478) and identified `company.find_all_active` as a custom finder, returning `"members.active"`

2. BUT the expansion logic (line 607) used `.search()` to find the FIRST method call in the code:
   ```python
   finder_match = method_call_pattern.search(code)  # Finds FIRST match
   ```

3. In code with multiple method calls, `.search()` found `VirtualCollection.new` first, not `company.find_all_active`

4. This caused incorrect expansion: `VirtualCollection.members.active` instead of `company.members.active`

## Solution

Modified `_parse_custom_finder_method()` to return information about WHICH method call was found:

### Change 1: Return Tuple from `_parse_custom_finder_method`

**Before:**
```python
def _parse_custom_finder_method(self, code: str) -> Optional[str]:
    # ... detection logic ...
    if method_body:
        return lines[-1]  # Just return method body
    return None
```

**After:**
```python
def _parse_custom_finder_method(self, code: str) -> Optional[tuple]:
    # ... detection logic ...
    if method_body:
        # Return tuple: (method_body, variable_name, method_name)
        return (lines[-1], variable_name, method_name)
    return None
```

### Change 2: Use Specific Pattern in Expansion Logic

**Before:**
```python
method_body = self._parse_custom_finder_method(code)
if method_body:
    # Generic pattern matches FIRST method call
    method_call_pattern = re.compile(r'\b(@?\w+)\.(\w+)([^#;{]*?)...')
    finder_match = method_call_pattern.search(code)  # BUG: finds first match
```

**After:**
```python
finder_info = self._parse_custom_finder_method(code)
if finder_info:
    method_body, found_var, found_method = finder_info

    # Build SPECIFIC pattern for the detected method call
    escaped_var = re.escape(found_var)
    escaped_method = re.escape(found_method)

    specific_method_pattern = re.compile(
        rf'\b(@?{escaped_var})\.({escaped_method})'  # Specific variable.method
        r'([^#;{]*?)'
        r'(?=\s*(?:#|;|{|\bdo\b|\bif\b|\bunless\b|\bend\b|$))'
    )
    finder_match = specific_method_pattern.search(code)  # Finds CORRECT match
```

## Verification

### Test 1: Isolated Code (was working, still works)
```python
code = "company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)"
conditions = parser.parse_ruby_code(code)
# Result: ✓ 5 conditions extracted
```

### Test 2: Code with Context (was broken, now fixed)
```python
code = '''VirtualCollection.new(page_size) do |page|
  company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)
end'''
conditions = parser.parse_ruby_code(code)
# Before fix: ✗ 1 condition (VirtualCollection_id)
# After fix:  ✓ 5 conditions (company_id, disabler_id, owner_id, login_handle, first_login_at)
```

### Test 3: Actual File Content
```ruby
# From alert_mailer.rb:180
else
  active_members = VirtualCollection.new(page_size) do |page|
    company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)
  end
end
```
**Result:** ✓ Successfully extracts 5 conditions, correctly ignoring `VirtualCollection.new`

## Files Modified

### `tools/components/where_clause_matcher.py`

**Lines 420-481:** Modified `_parse_custom_finder_method()` to return tuple
**Lines 589-636:** Modified expansion logic to use specific pattern matching

## Impact

This fix ensures that custom finder auto-detection works correctly even when:
- Code snippets contain multiple method calls
- The target method call is NOT the first one in the snippet
- There are surrounding context elements (blocks, assignments, etc.)

The fix maintains backward compatibility since the same test cases that worked before still pass.

## Related Files

- `tools/components/custom_finder_detector.py` - Custom finder detection logic (unchanged)
- `tests/test_custom_finder_auto_detection.py` - Unit tests for custom finder detection (all passing)
- `journal/2025-10-30_CUSTOM_FINDER_AUTO_DETECTION.md` - Original implementation notes
- `journal/2025-10-30_CUSTOM_FINDER_CHAIN_BUG_FIX.md` - Related fix for method chain preservation

## Next Steps

- ✓ Fix implemented and verified
- ✓ All test cases passing
- Consider adding regression test specifically for multi-method-call scenarios
- Monitor production usage to ensure no edge cases
