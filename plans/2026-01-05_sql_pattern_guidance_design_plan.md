# Plan: Enhanced SQL-to-Rails Pattern Generation Guidance

## Problem Statement
When users submit SQL queries to `ride_rails.py`, the LLM generates non-deterministic and often too-broad ripgrep patterns. For large codebases (3M+ LOC), patterns like `.where(id:` match thousands of files, making the search ineffective.

## Solution Overview
Two-part solution:
1. **Pattern Guidance**: Expand system prompt with principle-based guidance for pattern composition
2. **Goal Persistence**: Add periodic goal reminders to prevent agent drift (inspired by Cline's Focus Chain)

## Files to Modify
- `/Users/I503354/personal/ask-repo-agent/prompts/system_prompt.py` - Pattern reasoning guidance
- `/Users/I503354/personal/ask-repo-agent/agent/react_rails_agent.py` - Goal persistence injection

---

## Core Principles to Teach

### Principle 1: Every SQL Query Has a Model Context
```
SQL operates on tables → Rails operates on models
The model name is ALWAYS available context from the SQL
ANY pattern becomes more effective when combined with its model context
```

**Teaching**: Before searching for any pattern, the LLM should identify which model/table the query is about and ALWAYS include that context in the search pattern.

### Principle 2: Searchable vs Non-Searchable Elements
```
SEARCHABLE (exists in code):
- Column names (especially unusual/custom ones)
- Table names (especially compound names like `model_action_items`)
- String literals that look like identifiers
- Controller/action names embedded in data

NOT SEARCHABLE (runtime values):
- Numeric IDs (user_id = 123, id IN (...))
- Pagination offsets (OFFSET N - calculated at runtime)
- Counts, timestamps, calculated values
- Most numeric values (exceptions: config constants)
```

**Teaching**: The LLM should distinguish between code artifacts (searchable) and runtime data (not searchable). Don't waste searches on numeric IDs or offsets.

### Principle 3: Distinctiveness is Relative to Codebase Size
```
Before searching, estimate: "How many matches would this pattern produce?"

.where(              → thousands of matches (every model uses this)
.where(id:           → hundreds of matches (common finder)
unusual_column       → probably < 10 matches (custom column name)
Model.where(id:      → tens of matches (scoped to one model)
```

**Teaching**: The LLM should mentally assess distinctiveness and combine low-distinctiveness patterns with high-context patterns.

### Principle 4: Composition Multiplies Narrowing Power
```
Pattern A alone: 1000 matches
Pattern B alone: 500 matches
Pattern A + B combined: ~10-50 matches (intersection)

Single patterns are usually too broad. Combine:
- Model name + Rails method
- Distinctive column + Model context
- Multiple elements with .* for flexible ordering
```

**Teaching**: The LLM should default to composite patterns, not single-element patterns.

### Principle 5: Rails Naming Conventions Provide Multiple Search Angles
```
One concept has multiple searchable forms:
- Table: `models` (plural, snake_case)
- Model class: `Model` (singular, CamelCase)
- File: `model.rb`
- Variable: `model`, `@model`, `models`
- Association: `has_many :models`, `belongs_to :model`

Use case-insensitive search to catch variations.
```

**Teaching**: The LLM should leverage Rails conventions to construct patterns that match multiple forms of the same concept.

---

## The Reasoning Process (What to Add to Prompt)

```markdown
## SQL-to-Rails Pattern Reasoning

When searching for code that generates SQL, follow this reasoning process:

### Step 1: IDENTIFY Model Context
- Extract the table name from SQL
- Convert to model name (table `orders` → Model `Order`)
- This context will be part of every search pattern

### Step 2: EXTRACT Searchable Elements
- Column names (especially unusual ones)
- String values that look like identifiers
- Controller/action names if present in data
- SKIP: numeric IDs, offsets, timestamps (these are runtime values)

### Step 3: ASSESS Distinctiveness
For each element, ask: "In a large Rails codebase, how many files would match this?"
- < 50 matches: Can search alone
- 50-500 matches: Combine with model context
- > 500 matches: Must combine with multiple elements

### Step 4: COMPOSE Pattern
- Start with most distinctive searchable element
- Add model context (case-insensitive)
- Use .* to allow flexibility: "Model.*pattern|pattern.*Model"
- Use | for alternative orderings when element order varies

### Step 5: VERIFY Pattern Logic
- "Does this pattern reflect what Rails code would look like?"
- "Is this specific enough for a multi-million LOC codebase?"
- "Am I searching for code artifacts, not runtime values?"

<example>
SQL: SELECT * FROM orders WHERE user_id = 123 AND status = 'pending'

Searchable elements:
- Table: orders → Model: Order
- Column: status (common, needs context)
- String: 'pending' (might be searchable)

Patterns to try:
- "Order.*status.*pending|pending.*Order" (model + column + value)
- "Order.*\.where.*status" (model + method + column)
</example>

<example>
SQL: SELECT * FROM user_activity_logs WHERE action_type = 'login'

Searchable elements:
- Table: user_activity_logs → Model: UserActivityLog (distinctive!)
- Column: action_type
- String: 'login'

Patterns to try:
- "UserActivityLog" (distinctive table name alone may suffice)
- "user_activity_log" (file name search)
</example>
```

---

## Implementation Steps

### Step 1: Replace SQL Pattern Extraction Section (lines 73-82)
Replace the current minimal guidance with the principle-based reasoning framework above.

### Step 2: Add "What's Searchable" Guidance
Explicitly teach the distinction between code artifacts and runtime values. This prevents wasted searches on numeric IDs and offsets.

### Step 3: Add Pattern Composition Guidance
Teach that single patterns are usually too broad. The default should be:
```
ModelName.*distinctive_element|distinctive_element.*ModelName
```
with `case_insensitive=True`.

### Step 4: Add Transaction Log Reasoning (for multi-query logs)
```markdown
### Transaction Logs (BEGIN...COMMIT)
- First statement after BEGIN is usually the trigger (model being saved)
- Look for after_create, after_commit callbacks in that model
- Subsequent INSERTs often come from callbacks
- Search for distinctive table names from the transaction (feed tables, audit tables)
```

---

## Part 2: Goal Persistence (Inspired by Cline's Focus Chain)

### Problem
As the ReAct loop progresses and conversation grows, the agent can lose sight of the original SQL query and goal. This causes:
- Pattern drift (searching for tangentially related things)
- Premature completion (stopping before finding the actual source)
- Repeated searches (forgetting what was already tried)

### Solution: Periodic Goal Injection

Inject a goal reminder into the prompt every N steps (similar to Cline's `remindClineInterval`).

### Implementation in `react_rails_agent.py`

**Location**: `_build_context_prompt()` method (around line 380)

```python
def _build_context_prompt(self) -> str:
    """Build context-aware prompt including goal reminder."""
    available_tools = set(self.tool_registry.get_tool_names())
    base_prompt = self.state_machine.get_context_prompt(available_tools)

    # Goal persistence: remind every 5 steps
    step = self.state_machine.state.current_step
    if step > 0 and step % 5 == 0:
        # Extract original query from conversation
        original_query = self._get_original_user_query()
        if original_query:
            goal_reminder = self._generate_goal_reminder(original_query, step)
            base_prompt = goal_reminder + "\n\n" + base_prompt

    return base_prompt

def _get_original_user_query(self) -> str:
    """Get the first user message (the original query)."""
    for msg in self.conversation.history:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content[:500]  # Truncate for context efficiency
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")[:500]
    return ""

def _generate_goal_reminder(self, original_query: str, step: int) -> str:
    """Generate a goal reminder based on current progress."""
    tools_used = len(self.state_machine.state.tools_used)
    searches = [s for s in self.state_machine.state.steps
                if s.tool_name == "ripgrep"]

    reminder = f"""## Task Reminder (Step {step})

**Original Query:**
{original_query[:300]}{'...' if len(original_query) > 300 else ''}

**Progress:** {step} steps completed, {tools_used} unique tools used, {len(searches)} searches performed

**Goal:** Find the Rails source code that generates this SQL. Stay focused on:
1. Using composite patterns with model context
2. Searching for code artifacts, not runtime values
3. Verifying matches before concluding
"""
    return reminder
```

### When to Inject Goal Reminder

| Condition | Action |
|-----------|--------|
| Every 5 steps | Inject goal reminder |
| After 3+ searches with no high-confidence match | Inject with "try different approach" hint |
| User provides feedback | Reset step counter, inject updated goal |

### Expected Behavior

```
Step 1: User submits SQL query
Step 2: Agent searches (pattern A)
Step 3: Agent reads file
Step 4: Agent searches (pattern B)
Step 5: Agent sees → "## Task Reminder (Step 5)
                       Original Query: SELECT * FROM orders...
                       Goal: Find the Rails source code..."
Step 6: Agent stays focused, doesn't drift
...
Step 10: Another reminder injection
```

### Key Design Choices (Learning from Cline)

1. **Lightweight** - Just a prompt injection, no separate tool or file storage
2. **Periodic** - Every N steps, not every step (avoids token bloat)
3. **Includes Progress** - Shows steps/searches completed (like Cline's "5/10 items")
4. **Original Query Preserved** - First user message is the "north star"
5. **No User Intervention Required** - Automatic, unlike Cline's editable markdown

---

## Expected Prompt Content (~1500 tokens)

```markdown
# SQL-to-Rails Code Search Strategy

## Core Principle: Reason About Patterns, Don't Guess

### 1. Model Context is Always Available
Every SQL query comes from a model. Extract the table name, convert to model name,
and include it in your search pattern. "Model.*pattern" is always better than "pattern" alone.

### 2. Searchable vs Runtime Values

SEARCHABLE (exists in code):
- Column names (especially unusual/custom ones)
- Table names (especially compound names)
- String literals that look like identifiers
- Controller/action names embedded in data

NOT SEARCHABLE (runtime values):
- Numeric IDs (user_id = 123, id IN (...))
- Pagination offsets (OFFSET N - calculated at runtime)
- Counts, timestamps, calculated values

### 3. Rails Naming Conventions

One concept has multiple searchable forms:
- Table: `models` (plural, snake_case)
- Model class: `Model` (singular, CamelCase)
- File: `model.rb`
- Variable: `model`, `@model`, `models`
- Association: `has_many :models`, `belongs_to :model`

Use case-insensitive search to catch variations.

### 4. Assess Distinctiveness Before Searching
Ask: "How many files would match this in a large Rails app?"
- < 50 matches: Can search alone
- 50-500 matches: Combine with model context
- > 500 matches: Must combine with multiple elements

### 5. Compose Patterns by Default
Single patterns are too broad. Always combine Model + element.

<example>
SQL: SELECT * FROM orders WHERE user_id = 123 AND status = 'pending'

Searchable elements:
- Table: orders → Model: Order
- Column: status (common, needs context)
- String: 'pending' (might be searchable)

Patterns to try:
- "Order.*status.*pending|pending.*Order" (model + column + value)
- "Order.*\.where.*status" (model + method + column)
</example>

<example>
SQL: SELECT * FROM user_activity_logs WHERE action_type = 'login'

Searchable elements:
- Table: user_activity_logs → Model: UserActivityLog (distinctive!)
- Column: action_type
- String: 'login'

Patterns to try:
- "UserActivityLog" (distinctive table name alone may suffice)
- "user_activity_log" (file name search)
</example>

### 6. Transaction Logs (BEGIN...COMMIT)
- First INSERT/UPDATE after BEGIN is usually the trigger model
- Search for callbacks (after_create, after_commit) in that model
- Audit/logging table names are often distinctive - search those
```

---

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Approach | Principle-based reasoning | Teaches HOW to think, not patterns to copy |
| Pattern Location | System prompt | Maintains primitive-first architecture |
| Goal Persistence | Periodic prompt injection | Lightweight, no new tools/files needed |
| Reminder Interval | Every 5 steps | Balance between focus and token efficiency |
| Examples | Minimal | Principles over lookup tables |
| Token impact | ~1500 tokens (prompt) + ~200 tokens (reminder) | Acceptable overhead |

## Success Criteria

### Pattern Generation
1. LLM reasons about distinctiveness before searching
2. LLM always combines patterns with model context
3. LLM doesn't search for runtime values (IDs, offsets)
4. LLM uses composite patterns by default (Model.*element)
5. Works across any Rails repo without project-specific knowledge

### Goal Persistence
6. Agent doesn't drift from original SQL query goal
7. Agent sees progress summary (steps, searches) periodically
8. Long-running searches stay focused on finding source code

## Implementation Summary

| File | Change |
|------|--------|
| `prompts/system_prompt.py` | Add ~1500 tokens of pattern reasoning guidance |
| `agent/react_rails_agent.py` | Add `_generate_goal_reminder()` and inject every 5 steps |

## Testing

Test with example queries to verify:

1. **IN query with IDs**: LLM should recognize IDs are runtime values, search for "Model.*\.find|Model.*\.where\(id:" instead of the actual ID numbers
2. **Transaction log**: LLM should identify the first INSERT/UPDATE as trigger model, search for callbacks or distinctive table names
3. **Pagination query with OFFSET**: LLM should search for distinctive columns with Model context, not the OFFSET value
4. **Compound table name**: LLM should recognize distinctive table names (like `user_activity_logs`) can be searched alone

### Goal Persistence Test
5. **Long search (10+ steps)**: Verify agent sees goal reminders at steps 5 and 10, stays focused on original SQL query
