# Progressive Search Bug Fixes

**Date:** 2025-10-29
**Issue:** After refactoring to progressive search strategy, the tool failed to find matches that were previously found by the enhanced SQL search.

## Problem Statement

The refactored `sql_rails_search` tool (using progressive search) returned **0 matches** for a query that previously found **2 exact matches**:

```sql
SELECT `custom_domain_tombstones`.*
FROM `custom_domain_tombstones`
WHERE `custom_domain_tombstones`.`custom_domain` = ?
LIMIT ?
```

**Expected matches:**
- `lib/multi_domain.rb:43` - `CustomDomainTombstone.for_custom_domain(request_host).take`
- `app/models/company.rb:2987` - `CustomDomainTombstone.for_custom_domain(domain).take&.company`

## Root Causes

### Bug #1: Scope Pattern Regex Mismatch

**Location:** `tools/components/rails_search_rules.py:209`

**Problem:**
```python
# Old pattern (failed to match modern Rails syntax)
pattern = r"scope\s+:\w+.*custom_domain"
```

This pattern only matched old-style scope syntax:
```ruby
scope :name, -> { where(...) }  # MATCHED ✓
```

But failed to match modern parenthesis syntax:
```ruby
scope(:for_custom_domain, lambda do |custom_domain|  # NOT MATCHED ✗
```

**Fix:**
```python
# New pattern (handles both syntaxes)
pattern = r"scope\s*(?:[:(])?\s*:\w*custom_domain"
```

This now matches:
- `scope :name, ->` (old style)
- `scope(:name, lambda` (modern style)
- `scope( :name,` (alternate style)

### Bug #2: Premature Search Termination

**Location:** `tools/components/progressive_search_engine.py:182-220`

**Problem 1 - Skipping Valid Results:**
```python
# Old logic
if len(pattern_results) >= 20:
    # Skip pattern entirely
    continue
```

The `CustomDomainTombstone\.\w+` pattern found **40 matches** (including the correct 2), but was completely skipped due to the hard threshold.

**Problem 2 - Breaking After First Match:**
```python
# Old logic
if refined:
    results.extend(refined)
    break  # ❌ Stops searching for more patterns
```

After finding the scope definition, the search stopped immediately and never looked for usage sites in other files.

**Fix:**
```python
# New logic - refine even with many results
if pattern.distinctiveness >= 0.4 and len(pattern_results) > 0:
    if len(pattern_results) < 20:
        print(f"✓ Found {len(pattern_results)} results, refining...")
    else:
        print(f"⚠ Found {len(pattern_results)} results (many), refining to narrow down...")

    refined = self._refine_results(pattern_results, patterns[i+1:], sql_analysis)

    if refined:
        results.extend(refined)
        # Continue searching instead of breaking
        # (important for finding both definition AND usage sites)
    # ... handle other cases
```

## Results

**Before fixes:** 0 matches found ❌
**After fixes:** 9 matches found ✓

### Match Breakdown

**High Confidence (0.44):**
1. `app/models/custom_domain_tombstone.rb:34` - Scope definition
2. `lib/multi_domain.rb:43` - Usage with `.take` ✓
3. `app/models/concerns/multitenancy/company.rb:64` - Related usage
4. `app/models/company.rb:2435` - Related usage
5. `app/models/company.rb:2987` - Usage with `.take&.company` ✓

**Lower Confidence (0.20):**
6-9. Other CustomDomainTombstone usages (partial matches)

The two exact matches from the original screenshot are now correctly found (#2 and #5).

## Bonus Fix: Agent Presentation Issue

**Problem:** Even when the tool found both usage sites, the agent only presented one in the final response due to the system prompt instructing it to show "EXACT MATCH FOUND" (singular).

**Fix:** Updated `prompts/system_prompt.py` to:
1. Change "EXACT MATCH FOUND" → "MATCHES FOUND" (plural)
2. Add explicit instruction: "Show ALL matches found by the tool, categorized by type. Do not filter or hide any matches."
3. Provide categorization example (Definitions vs Usage Sites)
4. Reinforce in Response Requirements: "Never filter or hide matches found by tools. If the tool returns 5 matches, show all 5."

## Additional Fix: Bidirectional WHERE Validation

**Problem:** The validation logic had a **one-way check** that only verified SQL columns appeared in code, but didn't penalize code with **extra WHERE conditions**.

**Example False Positive:**
```sql
-- SQL we're searching for:
SELECT * FROM custom_domain_tombstones WHERE custom_domain = ? LIMIT ?

-- Code that got 0.44 confidence (same as exact matches!):
CustomDomainTombstone.find_by(company_id: ..., custom_domain: ...)
-- This generates: WHERE company_id = ? AND custom_domain = ?
```

These are **different queries** but got the same confidence score!

**Root Cause:**
```python
# Old validation (one-way check only)
matched_columns = sum(1 for col in sql_columns if col in code)
confidence = matched_columns / len(sql_columns)  # 1/1 = 1.0 ✓
# Missing: check if code has EXTRA columns!
```

**Fix:** Added bidirectional validation in `rails_search_rules.py:234-285`:

```python
# Extract columns from code using regex patterns
code_columns = extract_from(content, patterns=[
    r'where\s*\(\s*(\w+):',      # where(column:
    r'find_by\s*\(\s*(\w+):',    # find_by(column:
    # ...
])

# Check for extra columns in code not in SQL
sql_column_set = set(where_columns)
extra_columns = code_columns - sql_column_set

if extra_columns:
    # DIFFERENT QUERY - apply severe penalty
    confidence *= 0.3  # Reduce to 30% or less
```

**Results:**

| Match | Before | After | Reason |
|-------|--------|-------|--------|
| `.for_custom_domain(...).take` | 0.44 | 0.44 | ✓ Exact match (1 WHERE clause) |
| `.find_by(company_id:, custom_domain:)` | 0.44 ❌ | 0.27 ✓ | Different query (2 WHERE clauses) |
| `.find_or_create_by(company_id:, custom_domain:)` | 0.44 ❌ | 0.27 ✓ | Different query (2 WHERE clauses) |

The false positives are now correctly identified with lower confidence!

## Testing

All tests pass: ✓ **279 passed in 5.73s**

## Key Learnings

1. **Pattern matching must handle syntax variations** - Modern Rails uses both `scope :name` and `scope(:name)` syntaxes
2. **Threshold logic needs flexibility** - Fixed thresholds (e.g., "skip if >= 20 results") can miss valid matches
3. **Search needs to be comprehensive** - For Rails, you often need BOTH the definition (scope/method) AND usage sites (where it's called)
4. **LLM prompt engineering matters** - Even when tools provide all data, the prompt must explicitly instruct the agent not to filter results
5. **Validation must be bidirectional** - Don't just check if SQL columns appear in code; also penalize if code has EXTRA columns (indicates different query)

## Files Modified

1. `tools/components/rails_search_rules.py` - Fixed scope pattern regex + added bidirectional WHERE validation
2. `tools/components/progressive_search_engine.py` - Fixed search termination logic
3. `prompts/system_prompt.py` - Updated response format instructions
