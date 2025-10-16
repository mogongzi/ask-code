# Transaction Analyzer Hallucination Fix

**Date:** 2025-10-16
**Issues:**
1. Agent was hallucinating "EXACT MATCH" claims without providing file:line evidence
2. Agent was showing fake line numbers like "Line: Model callbacks (after_save)" instead of real numbers

## Problem Description

The transaction analyzer tool was extracting controller/action metadata from SQL comments and presenting it as `likely_source: "WorkPagesController#show_as_tab"` without actually verifying this file exists or searching for it. The agent then misinterpreted this inference as a verified match and claimed "EXACT MATCH FOUND in WorkPagesController" without providing any file path or line number.

**Examples of the problems:**

**Problem 1: Controller hallucination**
```
Agent output: "🎯 EXACT MATCH FOUND: PageView.create() call in WorkPagesController"
Actual tool result: No file path, no line number - just an inferred guess from SQL metadata
```

**Problem 2: Callback hallucination**
```
Agent output: "File: app/models/page_view.rb
             Line: Model callbacks (after_save)"
Actual tool result: Callback method name provided, but NO line number - just a suggestion
```

**Additional Problem**: Even after initial fix, tool was returning wrong line numbers - it found method DEFINITIONS (`def method_name`) instead of CALLBACK DECLARATIONS (`after_save :method_name`). For example, line 237 had the method definition, but the actual callback declaration was on line 15.

## Root Causes

### Controller Inference Issue
1. **Field naming issue**: `likely_source` suggested certainty when it was just an inference
2. **No verification**: SQL metadata was never verified against actual controller files
3. **Ambiguous presentation**: Summary didn't distinguish between verified vs inferred sources
4. **Agent misinterpretation**: Agent treated SQL metadata as concrete source locations

### Callback Suggestion Issue
1. **No line numbers**: `callback_investigation_suggestions` only provided method names, not line numbers
2. **Misleading field name**: "suggestions" were treated as verified locations by agent
3. **Agent fabrication**: Agent filled in fake "Line:" values with descriptive text instead of numbers

## Solutions Implemented

### 1. Renamed and Clarified Fields (transaction_analyzer.py:540-552)

**Before:**
```python
"likely_source": f"{ctrl.title().replace('_', '')}Controller#{act}"
```

**After:**
```python
"inferred_context": f"{ctrl.title().replace('_', '')}Controller#{act}",
"source_type": "sql_metadata",
"warning": "Inferred from SQL comments - not verified against actual source code"
```

### 2. Added Controller Verification (_verify_controller_context method, lines 571-669)

New verification strategy that:
- Extracts controller/action from SQL metadata
- Searches for actual controller file using ripgrep
- Finds the specific action method (e.g., `def show_as_tab`)
- Returns verified file path and line number
- Only claims "verified" when actual file is found

**Search flow:**
```
SQL metadata: controller:work_pages, action:show_as_tab
  → Search for: work_pages_controller.rb
    → Search in file for: "def show_as_tab"
      → Return: app/controllers/work_pages_controller.rb:42 (VERIFIED)
```

### 3. Updated Source Finding Priority (lines 581-596)

**New search priority:**
1. **Controller context verification** (HIGHEST) - verified file:line from SQL metadata
2. **Transaction fingerprint** - column signature matching in transaction blocks
3. **Individual query patterns** - per-query ActiveRecord search

### 4. Enhanced Summary Output (lines 950-1006)

Summary now clearly separates:

**✅ VERIFIED Controller Entry Point:**
```
📍 app/controllers/work_pages_controller.rb:42
   Method: def show_as_tab
   Confidence: verified (found in actual controller file)
   Source: SQL metadata verified against actual controller file
```

**💡 Inferred Context (not verified):**
```
• SQL comments suggest: WorkPagesController#show_as_tab
  ⚠️  Inferred from SQL comments - not verified against actual source code
```

### 5. Updated Compact Output (lines 164-192)

Compact mode now prioritizes:
1. `verified_controller` type
2. `transaction_wrapper` type
3. Falls back to "No source code matches found"

### 6. Added Callback Declaration Search (`_find_callback_declaration_line` method, lines 926-973)

**CRITICAL FIX**: Changed from searching for method definitions to searching for callback declarations.

**Problem**: The original fix searched for `def method_name` which found the method IMPLEMENTATION line.
But we need the CALLBACK DECLARATION line where `after_save :method_name` appears.

**Example of the problem**:
```ruby
# Line 15: This is what we WANT to find
after_save :publish_to_usage_auditing_feeds

# Line 237: This is what we were FINDING (wrong!)
def publish_to_usage_auditing_feeds
  # method implementation
end
```

**Solution**: New method that:
- Searches for the callback declaration line (e.g., `after_save :method_name`)
- NOT the method definition line (e.g., `def method_name`)
- Returns real line numbers when found
- Returns None if callback declaration doesn't exist

### 7. Updated Callback Extraction (`_extract_callback_suggestions` method, lines 871-924)

**Before:** Returned suggestions with NO line numbers
```python
{
    'method_name': 'publish_to_usage_auditing_feeds',
    'model_file': 'app/models/page_view.rb'
    # NO line number!
}
```

**After:** Returns verified callbacks WITH real line numbers of callback declarations
```python
{
    'method_name': 'publish_to_usage_auditing_feeds',
    'model_file': 'app/models/page_view.rb',
    'line': 15,  # Real line number of CALLBACK DECLARATION from ripgrep!
    'verified': True
}
```

**Key Change**: Line 15 points to `after_save :publish_to_usage_auditing_feeds`, NOT line 237 which has `def publish_to_usage_auditing_feeds`

### 8. Enhanced Callback Summary (lines 1008-1032)

Summary now separates:

**✅ VERIFIED Callback Methods:**
```
• PageView#publish_to_usage_auditing_feeds
  📍 app/models/page_view.rb:42
  Callback: after_save: publish_to_usage_auditing_feeds
  Reason: Likely generates multiple queries
```

**💡 SUGGESTED FOLLOW-UP (method definition not found):**
```
• PageView#some_missing_method
  Callback: after_save: some_missing_method
  ⚠️  Method definition not found in model file
  📖 Search manually in app/models/page_view.rb
```

## Test Coverage

Created `tests/test_transaction_analyzer_fix.py` with 4 test cases:

1. ✅ **test_inferred_context_has_warning** - Verifies warning fields exist
2. ✅ **test_controller_verification_separate_from_inference** - Verifies search strategy tags
3. ✅ **test_summary_separates_verified_from_inferred** - Verifies clear distinction in summary
4. ✅ **test_compact_output_prioritizes_verified_controller** - Verifies priority order

All tests passing ✓

## Impact

### Before Fixes:

**Controller hallucination:**
```
Agent: "🎯 EXACT MATCH FOUND: PageView.create() call in WorkPagesController"
[No file path, no line number provided]
```

**Callback hallucination:**
```
Agent: "File: app/models/page_view.rb
       Line: Model callbacks (after_save)"
[Fake line number - just descriptive text]
```

### After Fixes:

**Verified controller:**
```
Agent: "✅ VERIFIED Controller Entry Point:
  📍 app/controllers/work_pages_controller.rb:42
     Method: def show_as_tab
     Confidence: verified (found in actual controller file)"
```

**Verified callbacks:**
```
Agent: "✅ VERIFIED Callback Methods:
  • PageView#publish_to_usage_auditing_feeds
    📍 app/models/page_view.rb:15
    Callback: after_save: publish_to_usage_auditing_feeds
    Reason: Likely generates multiple queries"
```

**Critical**: Line 15 is the CALLBACK DECLARATION (`after_save :publish_to_usage_auditing_feeds`), NOT the method definition line (237)

**Inferred context (when verification fails):**
```
Agent: "💡 Inferred Context (from SQL metadata - not verified):
  • SQL comments suggest: WorkPagesController#show_as_tab
    ⚠️  Inferred from SQL comments - not verified against actual source code"
```

## Benefits

1. **No more hallucinations** - Agent can only claim "verified" when file:line exists (for both controllers AND callbacks)
2. **Real line numbers** - All locations now have actual line numbers from ripgrep, not fake descriptive text
3. **Clear distinction** - Users know when something is inferred vs verified
4. **Better accuracy** - Actual controller files AND callback methods are searched and validated
5. **Improved UX** - Summary clearly shows confidence levels with ✅ VERIFIED vs 💡 SUGGESTED markers
6. **Maintains performance** - Only searches when needed (SQL metadata present, priority callbacks detected)

## Files Modified

- `tools/transaction_analyzer.py` - Core improvements
- `tests/test_transaction_analyzer_fix.py` - New test coverage

## Migration Notes

- Old field `likely_source` removed - replaced with `inferred_context`
- New field `source_type` indicates metadata source
- New field `warning` provides user-facing disclaimer
- New search strategy: `controller_context_verification`
- Summary output format enhanced with clear verification markers

## Future Enhancements

1. Cache verified controller locations to avoid repeated searches
2. Add support for concern/module verification
3. Extend verification to service objects and background jobs
4. Add confidence scoring based on multiple signal correlation
