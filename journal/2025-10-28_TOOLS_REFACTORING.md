# Tools Architecture Refactoring

**Date:** 2025-10-28
**Type:** Architectural Refactoring
**Scope:** `tools/enhanced_sql_rails_search.py`, `tools/transaction_analyzer.py`, `tools/components/`

## Summary

Refactored the `enhanced_sql_rails_search` and `transaction_analyzer` tools to eliminate code duplication, remove cross-tool coupling, and improve separation of concerns. The two tools remain independent and focused, but now share common utilities for SQL analysis, code search, and Rails-specific operations.

## Problem Statement

The original architecture had several issues:

1. **Inappropriate Separation:** `enhanced_sql_rails_search` contained transaction detection logic (should only handle single queries)
2. **Hidden Coupling:** `transaction_analyzer` directly instantiated and called `enhanced_sql_rails_search` internally
3. **Code Duplication:** SQL parsing, ripgrep operations, and callback searches were duplicated across both tools
4. **Missing Abstractions:** No shared utilities for common operations (SQL classification, statement analysis, code location)

## Architectural Decision

**DO NOT MERGE** the tools. Instead, **REFACTOR** to maintain clear separation while extracting shared logic.

### Rationale

- `enhanced_sql_rails_search`: Analyze a **single SQL query** → Rails code mapping
- `transaction_analyzer`: Analyze a **complete transaction flow** → callbacks, patterns, data flow
- Different responsibilities, different use cases, should remain separate tools
- Problem is architectural (duplication), not conceptual (overlapping purposes)

## Changes Made

### Phase 1: Extract Shared Utilities

#### 1. Created `tools/components/sql_log_classifier.py`

**Purpose:** Centralized SQL input classification (single query vs. transaction log)

**Key Classes:**
- `SQLInputType` enum: Classification types (SINGLE_QUERY, TRANSACTION_LOG, EMPTY, UNRECOGNIZED)
- `ClassificationResult`: Classification output with confidence and reasoning
- `SQLLogClassifier`: Main classifier using `AdaptiveSQLExtractor` + heuristics

**Usage:**
```python
classifier = SQLLogClassifier()
result = classifier.classify(sql_input)

if result.is_transaction():
    # Route to transaction_analyzer
else:
    # Route to enhanced_sql_rails_search
```

**Impact:**
- Removed transaction detection from `enhanced_sql_rails_search` (was lines 291-328)
- Single source of truth for SQL input classification
- Used at orchestration layer to route to correct tool

---

#### 2. Created `tools/components/sql_statement_analyzer.py`

**Purpose:** Centralized SQL statement parsing (operation, table, columns extraction)

**Key Classes:**
- `StatementInfo`: Parsed statement information
- `SQLStatementAnalyzer`: Main analyzer for extracting statement metadata

**Key Methods:**
- `analyze(sql)` → StatementInfo: Complete statement analysis
- `extract_operation(sql)` → str: Operation type (INSERT, SELECT, UPDATE, etc.)
- `extract_table(sql, operation)` → Optional[str]: Primary table name
- `extract_columns(sql, operation)` → List[str]: Column names
- `extract_signature_columns(sql)` → List[str]: Distinctive columns (filters generic Rails timestamps)

**Usage:**
```python
analyzer = SQLStatementAnalyzer()
info = analyzer.analyze("INSERT INTO users (name, email) VALUES (...)")
# info.operation = 'INSERT'
# info.table = 'users'
# info.columns = ['name', 'email']
```

**Impact:**
- Replaced `_extract_operation` and `_extract_table` in `transaction_analyzer` (was lines 320-359)
- Eliminated duplicate SQL parsing logic
- Consistent operation/table extraction across tools

---

#### 3. Enhanced `tools/components/code_search_engine.py`

**Purpose:** Add context-aware ripgrep operations

**New Methods:**
- `search_with_context(pattern, file_ext, context_lines)`: Search with N lines of context after match
- `find_controller_file(controller_name)`: Find Rails controller file by name
- `find_method_definition(file_path, method_name)`: Find method definition line number
- `find_callback_declaration(model_file, callback_type, method_name)`: Find callback declaration line

**Usage:**
```python
engine = CodeSearchEngine(project_root)

# Find transaction blocks with 30 lines of context
blocks = engine.search_with_context(r"transaction\s+do", "rb", 30)

# Find controller action
line = engine.find_method_definition("app/controllers/users_controller.rb", "show")
```

**Impact:**
- Eliminated direct subprocess calls in both tools
- Consistent error handling and path normalization
- Context-aware searches for transaction wrapper detection

---

#### 4. Created `tools/components/rails_code_locator.py`

**Purpose:** Centralized Rails code location with caching

**Key Classes:**
- `ControllerLocation`: Controller action location info
- `CallbackLocation`: Callback declaration location info
- `RailsCodeLocator`: Main locator with caching

**Key Methods:**
- `find_controller_action(controller, action)` → Optional[ControllerLocation]: Find and cache controller action
- `find_callback(model_file, callback_type, method_name, model_name)` → Optional[CallbackLocation]: Find and cache callback
- `batch_find_callbacks(requests)`: Batch callback search for transactions

**Usage:**
```python
locator = RailsCodeLocator(project_root)
location = locator.find_controller_action("users", "show")
# location.file = "app/controllers/users_controller.rb"
# location.line = 42
# location.confidence = "verified (found in actual controller file)"
```

**Impact:**
- Replaced controller verification in `transaction_analyzer` (was lines 593-653)
- Replaced callback search in `transaction_analyzer` (was lines 829-876)
- Added caching to avoid re-searching same locations in transactions

---

### Phase 2: Remove Cross-Tool Coupling

#### 1. Updated `enhanced_sql_rails_search.py`

**Removed:**
- Lines 291-328: `_is_transaction_log()` and `_count_queries_in_log()` methods
- Transaction detection logic from `execute()` method

**Added:**
- Import of `SQLLogClassifier`
- Early classification check using `SQLLogClassifier.classify()`
- Cleaner error message when transaction detected

**Result:**
- Tool no longer knows about multi-query scenarios (proper separation)
- Delegates classification to shared utility
- Focused solely on single-query analysis

---

#### 2. Updated `transaction_analyzer.py`

**Removed:**
- Line 16: Import of `EnhancedSQLRailsSearch`
- Lines 714-751: Direct tool invocation code
- Lines 574-575: Local imports of subprocess/Path
- Lines 320-359: Duplicate `_extract_operation` and `_extract_table` methods

**Added:**
- Import of `SQLStatementAnalyzer`, `RailsCodeLocator`
- Import of `Path` at module level
- Architectural comment explaining orchestration layer responsibility
- Wrapper methods that delegate to shared utilities

**Updated:**
- `_extract_operation()`: Now delegates to `SQLStatementAnalyzer`
- `_extract_table()`: Now delegates to `SQLStatementAnalyzer`
- `_verify_controller_context()`: Now uses `RailsCodeLocator`
- `_find_callback_declaration_line()`: Now uses `RailsCodeLocator`

**Result:**
- No cross-tool coupling (tools are independent)
- Shared logic extracted to utilities
- Composition happens at orchestration layer

---

## Architecture Before vs. After

### Before (Problematic)

```
Agent
  ├─ enhanced_sql_rails_search.execute()
  │  ├─ [has transaction detection logic]  ❌ Wrong concern
  │  ├─ CodeSearchEngine.search() [inconsistent usage]
  │  ├─ SemanticSQLAnalyzer.analyze() [isolated instance]
  │  └─ Duplicate SQL parsing logic
  │
  └─ transaction_analyzer.execute()
     ├─ AdaptiveSQLExtractor.extract_all_sql()
     ├─ SemanticSQLAnalyzer.analyze() [duplicate instance]
     ├─ ModelAnalyzer.execute()
     ├─ EnhancedSQLRailsSearch.execute()  ❌ Tool calls tool!
     ├─ Duplicate SQL parsing logic
     └─ Direct ripgrep subprocess calls [inconsistent]
```

### After (Clean)

```
Agent (Orchestration Layer)
  ├─ SQLLogClassifier.classify() → routes to correct tool
  │
  ├─ enhanced_sql_rails_search.execute()
  │  ├─ SQLLogClassifier [rejects transactions]
  │  ├─ CodeSearchEngine [consistent usage]
  │  ├─ SemanticSQLAnalyzer
  │  └─ Focused on single queries ✅
  │
  └─ transaction_analyzer.execute()
     ├─ SQLStatementAnalyzer [shared parsing] ✅
     ├─ RailsCodeLocator [shared search, cached] ✅
     ├─ CodeSearchEngine [consistent usage]
     ├─ SemanticSQLAnalyzer
     ├─ ModelAnalyzer
     └─ Focused on transaction flow ✅
     └─ [No tool-to-tool coupling] ✅

Shared Utilities (tools/components/)
  ├─ sql_log_classifier.py
  ├─ sql_statement_analyzer.py
  ├─ code_search_engine.py (enhanced)
  └─ rails_code_locator.py (with caching)
```

---

## Benefits

### 1. Separation of Concerns
- Each tool has a single, focused responsibility
- Transaction detection moved to orchestration layer
- No tool-to-tool dependencies

### 2. Code Reuse
- SQL parsing logic unified in `SQLStatementAnalyzer`
- Code search consolidated in enhanced `CodeSearchEngine`
- Rails-specific searches in `RailsCodeLocator`

### 3. Performance
- Caching in `RailsCodeLocator` avoids redundant searches
- Consistent use of `CodeSearchEngine` reduces subprocess overhead
- Transaction analysis no longer re-searches same controllers/callbacks

### 4. Maintainability
- Single source of truth for SQL parsing
- Changes to ripgrep logic happen in one place
- Easier to test utilities independently

### 5. Consistency
- All tools use same classification logic
- All tools use same code search patterns
- Uniform error handling across tools

---

## Migration Notes

### For Orchestration Layer (react_rails_agent.py)

If transaction-level search finds insufficient matches, the agent should:

1. Check `transaction_analyzer` output for significant queries
2. Extract individual queries from transaction
3. Call `enhanced_sql_rails_search` for each query
4. Combine results for comprehensive coverage

**Example:**
```python
# In agent orchestration
result = transaction_analyzer.execute({"transaction_log": log})

if len(result["source_code_findings"]) < 2:
    # Not enough matches, fall back to individual query search
    for query in result["significant_queries"]:
        single_result = enhanced_sql_rails_search.execute({
            "sql": query["sql"],
            "max_results": 3
        })
        # Merge results...
```

### For Tool Users

No changes required! Both tools maintain the same public API:

- `enhanced_sql_rails_search.execute({"sql": "..."})`
- `transaction_analyzer.execute({"transaction_log": "..."})`

---

## Testing Recommendations

1. **SQLLogClassifier**: Test classification accuracy for various input types
2. **SQLStatementAnalyzer**: Test operation/table extraction for complex SQL
3. **RailsCodeLocator**: Test caching behavior, verify no stale results
4. **Integration**: Test both tools with shared utilities end-to-end
5. **Orchestration**: Test agent routing based on classification

---

## Future Improvements

### Phase 3: Pattern Matching Consolidation (Deferred)

The 6 strategy methods in `enhanced_sql_rails_search` (lines 352-755) could be refactored into a strategy registry pattern:

```python
class PatternMatchingStrategy:
    def match(analysis: QueryAnalysis) → List[SQLMatch]

DirectPatternStrategy()
ScopeBasedStrategy()
IntentBasedStrategy()
AssociationBasedStrategy()
ValidationBasedStrategy()
CallbackBasedStrategy()
```

This would:
- Reduce duplication across strategies
- Make patterns easier to test independently
- Allow dynamic strategy registration

**Status:** Deferred (not critical for current functionality)

### Phase 4: Model Analysis Caching

Add caching layer to avoid re-analyzing same model multiple times in a transaction:

```python
class ModelAnalysisCache:
    def get_or_analyze(model_name) → ModelAnalysis
    # Caches results per session/transaction
```

**Status:** Deferred (performance optimization, not architectural fix)

---

## Conclusion

This refactoring successfully addressed the architectural issues while maintaining the distinct responsibilities of each tool. The tools are now:

- ✅ **Independent:** No cross-tool coupling
- ✅ **Focused:** Each has a single, clear purpose
- ✅ **Maintainable:** Shared logic extracted to utilities
- ✅ **Performant:** Caching reduces redundant operations
- ✅ **Testable:** Utilities can be tested in isolation

The refactoring follows the **Single Responsibility Principle** and **Dependency Inversion Principle**, resulting in a cleaner, more maintainable codebase.
