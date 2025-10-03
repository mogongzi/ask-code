# Detailed Agent Flow: SQL Log Query Processing

This document traces the complete execution flow of how the ReAct Rails Agent processes your SQL transaction log query.

## Query Input
```
can you find the exact source code from the following sql log:
[... SQL transaction log with 16 queries ...]
```

---

## Phase 1: Initialization & Query Reception

### 1.1 CLI Entry Point (`ride_rails.py`)
```
User Input → ride_rails.py main() → get_agent_input()
```

**What happens:**
- User enters query in the interactive prompt
- `get_agent_input()` captures multi-line input
- Input is validated and passed to the agent

**Key files:**
- `ride_rails.py:41-100` - Input handling
- `util/simple_pt_input.py` - Prompt toolkit integration

### 1.2 Agent Initialization
```
main() → ReactRailsAgent(config, session)
```

**What happens:**
```python
# agent/react_rails_agent.py:35-66
def __init__(self, config, session):
    self.config = config or AgentConfig.create_default()
    self.tool_registry = ToolRegistry(project_root, debug)  # Register all tools
    self.state_machine = ReActStateMachine()                # Track ReAct state
    self.llm_client = LLMClient(session, console)           # LLM communication
    self.response_analyzer = ResponseAnalyzer()             # Parse LLM responses
```

**Components initialized:**
1. **ToolRegistry**: Loads and validates 10 Rails analysis tools
   - `ripgrep`, `enhanced_sql_rails_search`, `ast_grep`, `ctags`
   - `model_analyzer`, `controller_analyzer`, `route_analyzer`
   - `migration_analyzer`, `transaction_analyzer`, `file_reader`

2. **ReActStateMachine**: Manages agent state
   - Current step counter
   - Tool usage tracking
   - Stop conditions monitoring

3. **LLMClient**: Handles LLM communication
   - Streaming client setup
   - Tool execution integration
   - Response parsing

---

## Phase 2: ReAct Loop Execution

### 2.1 Process Message Entry
```
agent.process_message(user_query)
  ↓
_execute_react_loop(user_query)
```

**Location:** `agent/react_rails_agent.py:68-117`

**What happens:**
```python
def process_message(self, user_query: str) -> str:
    self.state_machine.reset()                    # Reset for new query
    self.conversation_history = []                # Clear history

    self.conversation_history.append({
        "role": "user",
        "content": user_query
    })

    response = self._execute_react_loop(user_query)  # Main loop
    return response
```

### 2.2 Build Initial Prompt
```python
# agent/react_rails_agent.py:128-132
messages = [
    {"role": "system", "content": RAILS_REACT_SYSTEM_PROMPT},
    {"role": "user", "content": f"Please analyze this Rails query: {user_query}"}
]
```

**System Prompt** (`prompts/system_prompt.py`):
- Defines agent role as Rails code analysis expert
- Lists all 10 available tools with schemas
- Provides ReAct pattern instructions:
  - **Thought**: Reasoning about next action
  - **Action**: Tool selection and parameters
  - **Observation**: Tool result analysis
  - **Answer**: Final response when done

---

## Phase 3: ReAct Step Loop

### Main Loop Structure
```python
# agent/react_rails_agent.py:134-150
while self.state_machine.should_continue(max_steps):
    step_num = self.state_machine.state.current_step + 1

    # 1. Call LLM with current messages
    llm_response = self._call_llm_with_tools(messages)

    # 2. Process LLM response
    should_stop = self._process_llm_response(llm_response, messages, step_num)

    if should_stop:
        break
```

**Stop conditions** (`agent/state_machine.py:should_continue()`):
- Max steps reached (15 steps)
- Explicit stop signal
- Final answer provided
- Too many consecutive no-tool-calls (3)

---

## Phase 4: Individual ReAct Steps (Your Query)

### 🔄 **STEP 1: Transaction Analysis**

#### 3.1 LLM Call
```
_call_llm_with_tools(messages)
  ↓
llm_client.call_with_tools(messages, available_tools)
  ↓
streaming_client.send_message(messages, tools)
```

**Location:** `agent/llm_client.py:30-60`

**What happens:**
```python
def call_with_tools(self, messages, available_tools):
    # Convert tools to OpenAI function calling format
    tool_schemas = [tool.to_function_schema() for tool in available_tools]

    # Send to LLM via streaming client
    response = self.streaming_client.send_message(
        messages=messages,
        tools=tool_schemas,
        tool_executor=self.tool_executor  # Executes tools during streaming
    )

    return response
```

#### 3.2 LLM Decision Making

**LLM analyzes your query and decides:**
- **Thought**: "This is a complete SQL transaction log with multiple queries. I should use the transaction_analyzer tool to analyze the entire flow."
- **Action**: Use `transaction_analyzer` tool
- **Parameters**:
  ```json
  {
    "transaction_log": "[entire SQL log string]"
  }
  ```

#### 3.3 Tool Execution (During Streaming)

```
streaming_client receives tool_call from LLM
  ↓
agent_tool_executor.execute_tool(tool_name, input_params)
  ↓
tool_registry.execute_tool("transaction_analyzer", params)
  ↓
TransactionAnalyzer.execute(params)
```

**Location:** `agent_tool_executor.py:30-70`

**What happens:**
```python
def execute_tool(self, tool_name: str, input_params: Dict) -> Any:
    # Debug logging
    self._debug_input(tool_name, input_params)

    # Execute tool
    result = self.tool_registry.execute_tool(tool_name, input_params)

    # Debug logging
    self._debug_output(tool_name, result)

    return result
```

#### 3.4 Transaction Analyzer Execution

**Location:** `tools/transaction_analyzer.py`

**What the tool does:**
1. **Parse SQL log**: Split into individual queries with timestamps
2. **Analyze patterns**:
   - Cascade inserts (page_views → audit_logs → feed items)
   - Read-modify-write patterns (SELECT + UPDATE)
   - Bulk operations (multiple UPDATEs on same table)
3. **Build data flow graph**: Track value propagation
4. **Detect callbacks**: Identify likely Rails callbacks
5. **Attempt model analysis**: Try to read Rails model files for each table
   - ⚠️ **Bug here**: Expects dict but gets list, causes errors like:
     ```
     Model analysis failed for PageView: 'list' object has no attribute 'items'
     ```
6. **Search for source code**: For each query, try to find Rails code
   - Uses `enhanced_sql_rails_search` internally
   - ⚠️ **Returns empty results** (more on this later)

**Output:** Large JSON with:
- Transaction summary (16 queries, 7 tables)
- Detected patterns (cascade_insert, read_modify_write, bulk_operation)
- Callback chains (page_views → audit_logs → feed_items)
- Data flow analysis
- Source code findings (EMPTY - the bug!)

#### 3.5 Observation Recorded

```python
# agent/react_rails_agent.py:180-195
observation = {
    "role": "assistant",
    "content": f"Tool '{tool_name}' returned:\n{tool_result}"
}
messages.append(observation)

# Record in state machine
self.state_machine.record_step(
    step_type=StepType.OBSERVATION,
    tool_name=tool_name,
    content=str(tool_result)
)
```

---

### 🔄 **STEP 4: Search for Controller Action**

#### LLM Decision
- **Thought**: "The transaction analyzer found the controller action is 'show_as_tab' in WorkPagesController. Let me search for this specific action."
- **Action**: Use `ripgrep` tool
- **Parameters**:
  ```json
  {
    "pattern": "work_pages.*show_as_tab",
    "file_types": ["rb"],
    "context": 5,
    "max_results": 10
  }
  ```

#### Tool Execution

**Location:** `tools/ripgrep_tool.py:77-150`

```python
def execute(self, input_params):
    pattern = input_params["pattern"]
    file_types = input_params.get("file_types", [])

    # Build ripgrep command
    cmd = ["rg", "--line-number", "--with-filename"]
    if case_insensitive:
        cmd.append("-i")
    cmd.extend(["-C", str(context)])  # Context lines

    for ftype in file_types:
        cmd.extend(["--type-add", f"target:*.{ftype}", "--type", "target"])

    cmd.extend([pattern, project_root])

    # Execute
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse output
    return parse_ripgrep_output(result.stdout)
```

**Result:** Found 1 match at `app/controllers/work_pages_controller.rb:602`

---

### 🔄 **STEP 7: Controller Analysis Attempt**

#### LLM Decision
- **Thought**: "Let me analyze the WorkPagesController to understand the show_as_tab action"
- **Action**: Use `controller_analyzer` tool
- **Parameters**:
  ```json
  {
    "controller_name": "WorkPages",
    "action": "show_as_tab"
  }
  ```

#### Tool Execution

**Location:** `tools/controller_analyzer.py:60-100`

```python
def execute(self, input_params):
    controller_name = input_params["controller_name"]
    action = input_params.get("action")

    # Construct expected file path
    # Bug: Removes spaces, creates "workpages" instead of "work_pages"
    snake_case = re.sub(r'(?<!^)(?=[A-Z])', '_', controller_name).lower()
    # Result: "workpages" ❌ (should be "work_pages")

    controller_path = f"{project_root}/app/controllers/{snake_case}_controller.rb"

    if not os.path.exists(controller_path):
        return {"error": f"Controller file not found: {controller_path}"}
```

**Result:** ❌ Error - file not found (looked for `workpages_controller.rb` instead of `work_pages_controller.rb`)

---

### 🔄 **STEP 9: Read File Directly**

#### LLM Decision
- **Thought**: "The controller analyzer failed. Let me read the file directly around line 602"
- **Action**: Use `file_reader` tool
- **Parameters**:
  ```json
  {
    "file_path": "app/controllers/work_pages_controller.rb",
    "line_start": 590,
    "line_end": 620
  }
  ```

#### Tool Execution

**Location:** `tools/file_reader_tool.py:45-90`

```python
def execute(self, input_params):
    file_path = input_params["file_path"]
    line_start = input_params.get("line_start", 1)
    line_end = input_params.get("line_end")

    # Make path absolute
    abs_path = os.path.join(project_root, file_path)

    # Read file
    with open(abs_path, 'r') as f:
        lines = f.readlines()

    # Extract range
    selected_lines = lines[line_start-1:line_end]

    # Format with line numbers
    content = "\n".join(
        f"  {line_start + i} | {line.rstrip()}"
        for i, line in enumerate(selected_lines)
    )

    return {
        "file_path": file_path,
        "total_lines": len(lines),
        "lines_shown": len(selected_lines),
        "line_range": [line_start, line_end],
        "content": content
    }
```

**Result:** ✅ Successfully read lines 590-620 showing the `@toggle_url` assignment but NOT the actual action method

---

### 🔄 **STEP 11: AST Search for Method**

#### LLM Decision
- **Thought**: "I found the URL generation but not the actual show_as_tab method. Let me search for the method definition."
- **Action**: Use `ast_grep` tool
- **Parameters**:
  ```json
  {
    "pattern": "def show_as_tab",
    "paths": ["app/controllers"],
    "max_results": 5
  }
  ```

#### Tool Execution

**Location:** `tools/ast_grep_tool.py:70-120`

```python
def execute(self, input_params):
    pattern = input_params["pattern"]
    paths = input_params.get("paths", ["."])

    # Build ctags command (uses universal-ctags or exuberant-ctags)
    cmd = ["ctags", "-x", "--language-force=Ruby"]

    for path in paths:
        full_path = os.path.join(project_root, path)
        cmd.append(full_path)

    # Execute ctags
    result = subprocess.run(cmd, capture_output=True, text=True)

    # Parse and filter by pattern
    matches = []
    for line in result.stdout.split('\n'):
        if pattern in line:
            matches.append(parse_ctags_line(line))

    return {"matches": matches, "total": len(matches)}
```

**Result:** ❌ 0 matches found (the method might be defined differently or ctags didn't index it)

---

### 🔄 **STEP 13: Enhanced SQL Search**

#### LLM Decision
- **Thought**: "Let me try searching for the specific INSERT INTO page_views query to find where PageView.create or PageView.new is called"
- **Action**: Use `enhanced_sql_rails_search` tool
- **Parameters**:
  ```json
  {
    "sql": "INSERT INTO `page_views` (...) VALUES (...)",
    "include_usage_sites": true,
    "max_results": 15
  }
  ```

#### Tool Execution Flow

**Location:** `tools/enhanced_sql_rails_search.py:77-170`

##### Step 13.1: Validate Input
```python
def execute(self, input_params):
    sql = input_params.get("sql", "").strip()

    # Check if transaction log
    if self._is_transaction_log(sql):
        return {"error": "Use transaction_analyzer instead"}

    # Proceed with single query analysis
```

##### Step 13.2: Semantic Analysis
```python
    # Use SQLGlot to parse SQL
    analysis = self.analyzer.analyze(sql)
```

**What SemanticSQLAnalyzer does** (`tools/semantic_sql_analyzer.py:129-151`):

```python
def analyze(self, sql: str) -> QueryAnalysis:
    # Parse SQL into AST
    parsed = sqlglot.parse(sql, dialect="postgres")[0]

    # Build analysis object
    analysis = QueryAnalysis(raw_sql=sql, intent=QueryIntent.DATA_RETRIEVAL)

    # Extract components
    self._extract_tables(parsed, analysis)        # Find table: page_views ✅
    self._extract_columns(parsed, analysis)       # Find columns
    self._extract_where_conditions(parsed, analysis)
    self._analyze_intent(parsed, analysis)        # Intent: DATA_INSERTION ✅
    self._infer_rails_patterns(analysis)          # Generate Rails patterns ✅

    return analysis
```

**Result of analysis:**
```python
QueryAnalysis(
    intent=QueryIntent.DATA_INSERTION,
    tables=[TableReference(name="page_views", rails_model="PageView")],
    rails_patterns=[
        "PageView.create(...)",
        "PageView.new(...).save",
        "build_page_view(...)"
    ],
    ...
)
```

##### Step 13.3: Create Fingerprint
```python
    fingerprint = create_fingerprint(analysis)
```

**Location:** `tools/semantic_sql_analyzer.py:419-456`

**🚨 BUG OCCURS HERE:**
```python
def create_fingerprint(analysis: QueryAnalysis) -> str:
    if analysis.intent == QueryIntent.EXISTENCE_CHECK:
        # ... handle existence checks
        return "SELECT 1 AS one FROM ..."

    elif analysis.intent == QueryIntent.COUNT_AGGREGATE:
        # ... handle counts
        return "SELECT COUNT(*) FROM ..."

    # ⚠️ NO CASE FOR DATA_INSERTION!
    # Falls through to default:

    table = analysis.primary_table.name if analysis.primary_table else "table"
    return f"SELECT * FROM {table}"  # ❌ Wrong for INSERT!
```

**Result:** `fingerprint = "SELECT * FROM table"` (useless!)

##### Step 13.4: Find Definition Sites
```python
    definition_matches = self._find_definition_sites_semantic(analysis)
```

**Location:** `tools/enhanced_sql_rails_search.py:611-630`

```python
def _find_definition_sites_semantic(self, analysis: QueryAnalysis) -> List[SQLMatch]:
    if not analysis.primary_model:  # Has "PageView" ✅
        return []

    # Try multiple strategies
    strategies = [
        self._strategy_direct_patterns,      # ⚠️ Doesn't search for .create/.save!
        self._strategy_intent_based,
        self._strategy_association_based,
        self._strategy_validation_based,
        self._strategy_callback_based
    ]

    all_matches = []
    for strategy in strategies:
        matches = strategy(analysis)
        all_matches.extend(matches)

    return all_matches
```

**Strategy: Direct Patterns** (`_strategy_direct_patterns`, lines 632-661):

```python
def _strategy_direct_patterns(self, analysis):
    matches = []

    for pattern in analysis.rails_patterns:  # Has: PageView.create(...), PageView.new(...).save
        if ".exists?" in pattern:
            # Search for .exists? ✅
            found = self._search_pattern(r"\.exists\?\b", "rb")
            # Filter by model name
            # Add to matches

        elif ".count" in pattern:
            # Search for .count ✅
            found = self._search_pattern(r"\.count\b", "rb")
            # ...

        # ⚠️ NO CASE FOR .create, .new, or .save!
        # Patterns are ignored!

    return matches  # Empty!
```

**🚨 BUG #2: Missing search patterns for INSERT operations**

##### Step 13.5: Search Scope Issue

Even if the search patterns existed, the `_search_pattern` method likely uses:

```python
def _search_pattern(self, pattern, file_type):
    # Searches in typical Rails directories
    search_paths = [
        f"{project_root}/app/models",
        f"{project_root}/app/controllers",
        f"{project_root}/app/helpers",
        # ⚠️ Missing: lib/ directory!
    ]
```

**🚨 BUG #3: The actual code is in `lib/page_view_helper.rb`, not in `app/`**

**Final Result:**
```json
{
  "fingerprint": "SELECT * FROM table",
  "matches": [],  // ❌ EMPTY
  "verify": "rails runner 'puts PageView.new.save'",
  "sql_analysis": {...}
}
```

---

### 🔄 **STEP 15: Model Analysis**

#### LLM Decision
- **Thought**: "Let me analyze the PageView model to understand its callbacks, which might explain the cascade"
- **Action**: Use `model_analyzer` tool
- **Parameters**:
  ```json
  {
    "model_name": "PageView",
    "focus": "all"
  }
  ```

#### Tool Execution

**Location:** `tools/model_analyzer.py:80-150`

```python
def execute(self, input_params):
    model_name = input_params["model_name"]
    focus = input_params.get("focus", "all")

    # Find model file
    model_path = f"{project_root}/app/models/{snake_case(model_name)}.rb"

    if not os.path.exists(model_path):
        return {"error": "Model not found"}

    # Read and parse model file
    with open(model_path) as f:
        content = f.read()

    # Extract components
    associations = self._extract_associations(content)
    callbacks = self._extract_callbacks(content)
    validations = self._extract_validations(content)
    methods = self._extract_methods(content)

    return {
        "associations": associations,
        "callbacks": callbacks,
        "validations": validations,
        "methods": methods
    }
```

**Result:** ✅ Successfully found PageView model at `app/models/page_view.rb:60-88`

**Key findings:**
- Callbacks:
  - `after_save :publish_to_usage_auditing_feeds` ← This triggers audit_logs!
  - `after_save :notify_content_viewed_event_subscriptions`
  - `after_commit :trigger_search_update`
  - `after_create :add_to_gamifeed`
- Associations: belongs_to company, owner, member, group, content

---

### 🔄 **STEP 16: Final Answer**

#### LLM Decision
- **Thought**: "I've gathered information about the transaction patterns, found the controller code, and identified the PageView callbacks. I should provide my findings."
- **Action**: None (final answer)

#### Stop Condition Met
```python
# agent/state_machine.py:should_continue()
if self.state.current_step >= max_steps:
    return False  # Stop

# OR if LLM provides final answer without tool call
if response has no tool_calls and has assistant message:
    return False  # Stop
```

---

## Phase 5: Response Assembly

### 5.1 Extract Final Response
```python
# agent/react_rails_agent.py:150-165
final_response = self._extract_final_response(messages)
```

**What happens:**
- Looks for last assistant message without tool calls
- Formats the response for display
- Includes any markdown/code blocks

### 5.2 Log Completion
```python
duration_ms = (time.time() - start_time) * 1000

log_agent_complete(
    duration_ms=45884,
    steps_completed=16,
    tools_used=7,
    success=True
)
```

---

## Summary: Why the Search Failed

### Root Causes

1. **Bug in `transaction_analyzer`**:
   - Model analysis crashes with `'list' object has no attribute 'items'`
   - Source code search returns empty results

2. **Bug in `enhanced_sql_rails_search`**:
   - **Missing INSERT fingerprint**: Returns generic `"SELECT * FROM table"`
   - **Missing search patterns**: Doesn't look for `.create(`, `.new(`, or `.save!`
   - **Limited search scope**: Doesn't search `lib/` directory

3. **Bug in `controller_analyzer`**:
   - Name conversion bug: `WorkPages` → `workpages` instead of `work_pages`

4. **Missing method definition**:
   - `show_as_tab` method likely uses Rails route conventions or is inherited/included
   - Not explicitly defined in the controller file

### What the Agent Found

✅ **Successfully identified:**
- Transaction flow and patterns
- Callback chains (page_views → audit_logs → feeds)
- Data flow between queries
- PageView model callbacks
- Controller context (work_pages_controller.rb:602)

❌ **Failed to find:**
- Actual source code that creates PageView (`PageView.new` in `lib/page_view_helper.rb`)
- The `log_page_view` helper method
- The `show_as_tab` controller action

### The Missing Code

The actual code is in `/Users/I503354/jam/local/ct/lib/page_view_helper.rb:2-32`:

```ruby
def log_page_view(model_instance, owner_id, mi=nil)
  ActiveRecord::Base.transaction do
    page_view = PageView.new(
      :content => model_instance,
      :member => @logged_in_user,
      :company_id => @logged_in_user.company_id,
      :action => params[:action],
      :controller => params[:controller],
      # ... more attributes
    )
    page_view.save!  # ← This triggers the entire cascade!
  end
end
```

This code is:
1. In `lib/` directory (not searched)
2. Uses `PageView.new` + `.save!` pattern (not searched for)
3. Wrapped in transaction (matches the SQL log)
4. Sets controller/action from params (matches the SQL INSERT)

---

## Architecture Diagram

```
ride_rails.py
    ↓
ReactRailsAgent.process_message()
    ↓
_execute_react_loop()
    │
    ├─→ Build system prompt with tool schemas
    │
    └─→ LOOP: while should_continue()
            │
            ├─→ _call_llm_with_tools(messages)
            │       │
            │       ├─→ LLMClient.call_with_tools()
            │       │       │
            │       │       └─→ StreamingClient.send_message()
            │       │               │
            │       │               └─→ HTTP POST to LLM endpoint
            │       │                       │
            │       │                       ├─→ LLM generates response
            │       │                       │   - Thought
            │       │                       │   - Tool call(s)
            │       │                       │
            │       │                       └─→ During streaming:
            │       │                               │
            │       │                               └─→ AgentToolExecutor.execute_tool()
            │       │                                       │
            │       │                                       └─→ ToolRegistry.execute_tool()
            │       │                                               │
            │       │                                               └─→ Specific tool.execute()
            │       │
            │       └─→ Returns response with tool results
            │
            ├─→ _process_llm_response()
            │       │
            │       ├─→ ResponseAnalyzer.analyze()
            │       │       - Parse thought/action/observation
            │       │       - Extract tool calls and results
            │       │
            │       ├─→ StateMachine.record_step()
            │       │       - Track step type
            │       │       - Update tool stats
            │       │
            │       └─→ Append to messages[]
            │               - Add tool results as observations
            │
            └─→ Check stop conditions
                    - Max steps (15)
                    - Final answer provided
                    - Consecutive no-tool-calls (3)
```

---

## Key Data Structures

### Messages Array (LLM Context)
```python
messages = [
    {
        "role": "system",
        "content": RAILS_REACT_SYSTEM_PROMPT  # Tool schemas + instructions
    },
    {
        "role": "user",
        "content": "Please analyze this Rails query: [your SQL log]"
    },
    {
        "role": "assistant",
        "content": None,
        "tool_calls": [{
            "id": "call_abc123",
            "function": {
                "name": "transaction_analyzer",
                "arguments": "{\"transaction_log\": \"...\"}"
            }
        }]
    },
    {
        "role": "tool",
        "tool_call_id": "call_abc123",
        "content": "{\"transaction_summary\": \"...\", ...}"
    },
    # ... more steps
]
```

### State Machine State
```python
state = {
    "current_step": 16,
    "steps": [
        {"type": "thought", "content": "...", "step": 1},
        {"type": "action", "content": "...", "tool": "transaction_analyzer", "step": 1},
        {"type": "observation", "content": "...", "step": 1},
        # ... more steps
    ],
    "tools_used": [
        "transaction_analyzer",
        "ripgrep",
        "controller_analyzer",
        "file_reader",
        "ast_grep",
        "enhanced_sql_rails_search",
        "model_analyzer"
    ],
    "tool_stats": {
        "transaction_analyzer": 1,
        "ripgrep": 1,
        "controller_analyzer": 1,
        "file_reader": 1,
        "ast_grep": 1,
        "enhanced_sql_rails_search": 1,
        "model_analyzer": 1
    },
    "finalize_requested": False,
    "should_stop": True,
    "stop_reason": "max_steps_reached"
}
```

---

## File Reference Map

| Component | File | Key Lines |
|-----------|------|-----------|
| CLI Entry | `ride_rails.py` | 1-300 |
| Agent Core | `agent/react_rails_agent.py` | 27-250 |
| State Machine | `agent/state_machine.py` | 15-200 |
| LLM Client | `agent/llm_client.py` | 10-100 |
| Tool Executor | `agent_tool_executor.py` | 15-120 |
| Tool Registry | `agent/tool_registry.py` | 20-150 |
| System Prompt | `prompts/system_prompt.py` | 1-500 |
| Transaction Analyzer | `tools/transaction_analyzer.py` | 40-500 |
| SQL Search | `tools/enhanced_sql_rails_search.py` | 39-800 |
| SQL Analyzer | `tools/semantic_sql_analyzer.py` | 123-500 |
| Model Analyzer | `tools/model_analyzer.py` | 25-200 |
| Ripgrep Tool | `tools/ripgrep_tool.py` | 25-250 |

---

## Next Steps for Fixing

1. **Fix `create_fingerprint` for INSERT queries**
2. **Add search patterns for `.create`, `.new`, `.save` in `_strategy_direct_patterns`**
3. **Expand search scope to include `lib/` directory**
4. **Fix controller name conversion bug in `controller_analyzer`**
5. **Fix model analysis dict/list type error in `transaction_analyzer`**