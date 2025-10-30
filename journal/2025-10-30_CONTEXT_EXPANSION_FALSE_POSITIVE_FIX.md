# Context Expansion False Positive Fix

**Date:** 2025-10-30
**Status:** ✓ Fixed and Verified
**Files Modified:** `tools/components/progressive_search_engine.py`

## Problem

Both line 176 and line 180 in alert_mailer.rb were showing "✓ All 5 WHERE conditions matched" with confidence 1.00, even though line 176 only has 4 conditions (missing `company_id`).

### The Two Lines

**Line 176:** `Member.active.offset(...).limit(...).order(...)`
- Should extract: 4 conditions (login_handle, owner_id, disabler_id, first_login_at)
- Missing: `company_id` condition

**Line 180:** `company.find_all_active.offset(...).limit(...).order(...)`
- Should extract: 5 conditions (company_id + 4 from active scope)
- Complete match for the SQL

### SQL Query
```sql
SELECT * FROM members
WHERE company_id = 32546
AND login_handle IS NOT NULL
AND owner_id IS NULL
AND disabler_id IS NULL
AND first_login_at IS NOT NULL
```

## Root Cause

The progressive search engine's context expansion was too aggressive:

```ruby
# File: alert_mailer.rb lines 173-181
if company.nil?
  active_members = VirtualCollection.new(page_size) do |page|
    Member.active.offset((page-1)*page_size).limit(page_size).order(id: :asc)  ← Line 176
  end
else
  active_members = VirtualCollection.new(page_size) do |page|
    company.find_all_active.offset((page-1)*page_size).limit(page_size).order(id: :asc)  ← Line 180
  end
end
```

**The Bug:**
- Context expansion used `lines_before=3, lines_after=5`
- For line 176, this expanded to lines 173-181
- The expanded context included **BOTH** the `if` branch AND the `else` branch
- The WHERE clause parser extracted conditions from BOTH branches
- Result: Line 176 appeared to have 5 conditions (including `company.find_all_active` from line 180!)

## The Fix

**File:** `tools/components/progressive_search_engine.py:591`

**Before:**
```python
expanded_content = self._expand_context(str(full_path), line_num, lines_before=3, lines_after=5)
```

**After:**
```python
# Reduced lines_after from 5 to 2 to avoid including else branches
expanded_content = self._expand_context(str(full_path), line_num, lines_before=3, lines_after=2)
```

**Reasoning:**
- `lines_after=2` is sufficient to capture method chains and association patterns
- Prevents including separate control flow branches (if/else, case/when)
- For line 176, context now only includes lines 173-178 (ends at `else`, doesn't include line 180)

## Verification

### Before Fix
```
Search Results:
1. alert_mailer.rb:176
   Confidence: 1.00
   Why: ✓ All 5 WHERE conditions matched  ← WRONG!

2. alert_mailer.rb:180
   Confidence: 1.00
   Why: ✓ All 5 WHERE conditions matched  ← CORRECT
```

### After Fix
```
Search Results:
1. alert_mailer.rb:180
   Confidence: 1.00
   Why: ✓ All 5 WHERE conditions matched  ← CORRECT

(Line 176 no longer in top matches - correctly filtered due to missing company_id)
```

## Direct Verification

```python
# Test with reduced context expansion
tool = SQLRailsSearch(project_root="/Users/I503354/jam/local/ct")
result = tool.execute({"sql": sql_with_5_conditions})

# Result:
# - Line 176: Not in top matches (missing company_id condition)
# - Line 180: Confidence 1.00 (all 5 conditions matched)
```

## Impact

This fix ensures that:
1. ✓ Only line 180 matches the SQL (correct!)
2. ✓ Line 176 is filtered out (missing company_id)
3. ✓ Context expansion doesn't leak conditions from unrelated code paths
4. ✓ Control flow branches (if/else) don't cross-contaminate

## Trade-offs

**Pros:**
- Eliminates false positives from control flow branches
- More accurate confidence scoring
- Better ranking of results

**Potential Cons:**
- Slightly less context for complex association chains
- May miss some edge cases where relevant code is 3+ lines after the match

**Mitigation:**
- `lines_before=3` still provides sufficient context for most cases
- `lines_after=2` captures immediate method chains
- Custom finder auto-detection handles complex method bodies

## Related Fixes

- `journal/2025-10-30_CUSTOM_FINDER_CONTEXT_BUG_FIX.md` - Custom finder expansion bug
- `journal/2025-10-30_CUSTOM_FINDER_AUTO_DETECTION.md` - Auto-detection implementation
- `journal/2025-10-30_CUSTOM_FINDER_CHAIN_BUG_FIX.md` - Method chain preservation

## Future Improvements

Consider implementing **control-flow-aware parsing**:
- Detect Ruby control structures (if/else, case/when, begin/rescue)
- Only extract conditions from the branch containing the matched line
- Would allow larger context windows without cross-contamination

This would be more robust than limiting context size, but requires more complex parsing logic.
