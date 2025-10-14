# Transaction Analysis Improvements

**Date**: 2025-10-14

## Problem Statement

The agent was generating final answers without investigating callback implementations when analyzing SQL transactions. For example, when analyzing a page view transaction with 16 queries triggered by `PageView.save!`, the agent would:

1. ✅ Find the transaction wrapper (`lib/page_view_helper.rb:4`)
2. ✅ Identify callbacks mentioned in the model (`after_save :publish_to_usage_auditing_feeds`)
3. ❌ **Stop without reading callback implementations**
4. ❌ User left wondering what `publish_to_usage_auditing_feeds` actually does

## Solution Implemented

Three interconnected improvements to guide the agent toward deeper investigation:

### 1. Enhanced System Prompt (`prompts/system_prompt.py`)

**Added Callback Investigation Protocol:**
```
**Callback Investigation Protocol:**
When you find code with ActiveRecord callbacks (after_save, after_create, etc.), you MUST:
1. Identify callback method names from the model analysis
2. Use `file_reader` to read the callback implementations
3. For complex transactions, trace 2-3 key callbacks that generate the bulk of queries
4. Include actual callback code snippets in your final response
```

**Added New Response Section:**
```
### 5. 🔍 Callback Deep Dive (For Transactions with Callbacks)

When the transaction involves callbacks, provide implementation details:

**Format:**
- **Callback Name**: `after_save :publish_to_usage_auditing_feeds`
- **File**: `app/models/page_view.rb:237-245`
- **Implementation**:
  ```ruby
  def publish_to_usage_auditing_feeds
    # Show the actual code here
  end
  ```
- **SQL Generated**: List which queries from the transaction this callback produces
```

### 2. Response Analyzer Enhancement (`agent/response_analyzer.py`)

**Added Callback Completeness Check:**
```python
def _has_callbacks_needing_investigation(self, response: str, react_state: ReActState) -> bool:
    """Check if response mentions callbacks that haven't been investigated yet."""
    # Detects callback mentions (after_save :method_name)
    # Checks if transaction involves multiple queries
    # Returns True if callbacks mentioned but implementations not shown
```

**Integration with Final Answer Detection:**
The `_check_semantic_final_patterns` method now checks for callback investigation needs BEFORE declaring a response as final:

```python
# IMPORTANT: Check if callbacks need investigation before declaring final
if self._has_callbacks_needing_investigation(response, react_state):
    return AnalysisResult(
        is_final=False,
        confidence="medium",
        reason="Response mentions callbacks but implementations not yet investigated",
        suggestions=["Read callback implementations for complete understanding"],
        has_concrete_results=True
    )
```

### 3. Transaction Analyzer Suggestions (`tools/transaction_analyzer.py`)

**Added Callback Suggestion Extraction:**
```python
def _extract_callback_suggestions(self, model_analysis: Dict[str, Any]) -> List[Dict[str, str]]:
    """Extract suggestions for which callbacks to investigate further."""
    # Prioritizes callbacks with keywords: save, create, commit, feed, audit, aggregate, publish
    # Returns top 3 most important callbacks with file paths and reasons
```

**Enhanced Transaction Summary Output:**
The transaction analyzer now includes a "SUGGESTED FOLLOW-UP" section in its summary:

```
💡 SUGGESTED FOLLOW-UP: Investigate these callback implementations:
  • PageView#publish_to_usage_auditing_feeds
    Callback: after_save: publish_to_usage_auditing_feeds
    Reason: Likely generates multiple queries (feed/audit/aggregate pattern)
    📖 Use file_reader on app/models/page_view.rb to see implementation
```

**Added to Return Structure:**
```python
return {
    ...
    "callback_investigation_suggestions": callback_suggestions  # NEW
}
```

## Expected Behavior Now

When analyzing the same page view transaction:

1. ✅ Find transaction wrapper (`lib/page_view_helper.rb:4`)
2. ✅ Identify callbacks in PageView model
3. ✅ **Transaction analyzer suggests investigating `publish_to_usage_auditing_feeds`**
4. ✅ **Response analyzer prevents premature finalization**
5. ✅ **Agent reads callback implementations with `file_reader`**
6. ✅ **Agent includes callback code in final response**

## Example Improved Flow

**Step 1**: Agent uses `transaction_analyzer`
- Gets transaction summary with callback suggestions
- Sees: "💡 Investigate PageView#publish_to_usage_auditing_feeds"

**Step 2**: Response analyzer checks response
- Detects callbacks mentioned but not investigated
- Returns: `is_final=False`, suggests reading implementations

**Step 3**: Agent uses `file_reader`
- Reads `app/models/page_view.rb` for callback methods
- Gets actual implementation of `publish_to_usage_auditing_feeds`

**Step 4**: Agent generates comprehensive final answer
- Includes transaction wrapper code
- Includes callback implementations with line numbers
- Shows which queries each callback generates

## Benefits

1. **Deeper Understanding**: Users get complete picture of transaction flow
2. **Faster Debugging**: See actual callback code without manual investigation
3. **Better Accuracy**: Agent provides implementation details, not just mentions
4. **Improved Confidence**: Concrete code evidence increases trust in results

## Testing

All existing tests pass:
```bash
pytest tests/test_transaction_analyzer_log_parsing.py -v
# ✅ PASSED
```

## Token Optimization (v2)

After initial implementation showed 150k token usage (doubled from baseline), implemented aggressive optimizations:

### Optimization Strategies

**1. Compact Model Analysis**
- **Before**: Returned full model analysis with all methods, validations, scopes
- **After**: Returns only callbacks + associations (removed `analysis` field)
- **Savings**: ~50-70% reduction in model analysis payload

**2. Limited Callback Investigation**
- **Before**: Suggested investigating top 3 callbacks
- **After**: Suggests only top 2 most impactful callbacks
- **Savings**: 33% fewer follow-up file reads

**3. Targeted File Reading**
- **Before**: `file_reader(app/models/page_view.rb)` (entire file, ~200 lines)
- **After**: `ripgrep` to find method → `file_reader` with line ranges (20-30 lines)
- **Savings**: ~80% reduction per file read

**4. Smart Callback Filtering**
- Only suggests callbacks with keywords: save, create, commit, feed, audit, aggregate, publish
- Skips generic callbacks unlikely to generate complex queries
- **Savings**: Fewer irrelevant investigations

### Expected Token Usage

**Baseline (no callback investigation)**: ~75k tokens
**With improvements (unoptimized)**: ~150k tokens (+100%)
**With optimizations (v2)**: ~95-110k tokens (+30-45%)

**Breakdown**:
- Transaction analyzer: 5-8k (was 15-20k)
- Model analysis: 3-5k per model (was 8-12k)
- Callback investigation: 2-3k per callback (was 5-7k)
- Final response: 1-2k (was 1-2k)

## Finalization Fix (v3)

After optimization, discovered the agent was stuck in infinite investigation loop:
- Transaction analyzer suggested callbacks ✅
- Agent investigated callbacks ✅
- Agent kept finding MORE callbacks to investigate ❌
- Never reached final answer ❌

### Root Cause
`_has_callbacks_needing_investigation()` returned True on EVERY step that mentioned callbacks, causing infinite loop.

### Solution
Added **investigation depth tracking** to response analyzer:

```python
# OPTIMIZATION 1: Stop after 3 file_reader calls
file_reader_count = react_state.tool_stats.get('file_reader', None)
if file_reader_count and file_reader_count.usage_count >= 3:
    return False  # Already investigated enough

# OPTIMIZATION 2: Stop after step 6
if react_state.current_step >= 6:
    return False

# OPTIMIZATION 3: Check if already investigated
has_def_patterns = response.count('def ') >= 2  # At least 2 method definitions shown
has_file_reads = file_reader_count and file_reader_count.usage_count >= 1

if has_file_reads and has_def_patterns:
    return False  # Already investigated, allow finalization
```

### Updated System Prompt
Changed callback investigation from "MUST" to "MAY" with explicit limits:
- **Maximum file reads**: 3 reads total
- **Maximum steps**: Stop by step 6-7
- **Focus**: PRIMARY trigger callbacks only

### Expected Behavior Now
1. Step 1: Transaction analyzer (finds wrapper + suggests callbacks)
2. Step 2-3: Ripgrep + file_reader for 1-2 key callbacks
3. Step 4: **Agent synthesizes final answer** ✅

## Trade-offs

- **Execution Time**: +1-2 additional steps for callback investigation
- **Context Usage**: +30-45% tokens (optimized from +100%)
- **Complexity**: More sophisticated response analysis logic
- **Completeness**: Investigates 1-2 key callbacks (not all callbacks)
- **Finalization**: Hard limits prevent investigation loops

## Success Metrics

**Before**: Agent stopped after 3-4 steps with transaction wrapper found
**After**: Agent continues for 5-6 steps, investigating 2-3 key callbacks

**Before**: Final response ~600 tokens (wrapper + callbacks list)
**After**: Final response ~900 tokens (wrapper + callback implementations + SQL mapping)

**Before**: User must manually investigate callbacks
**After**: User gets complete implementation details automatically
