# Structured Reasoning for Deterministic Agent Behavior

**Date:** 2026-01-04
**Feature:** Structured Reasoning Injection
**Status:** Planning

## Problem Statement

When running the same query twice against the LLM-based Rails agent, we get different results due to:

1. **LLM Non-determinism**: Even with temperature=0, token sampling has inherent randomness
2. **Path-dependent exploration**: Early tool choices cascade into completely different search paths
3. **No enforced analysis sequence**: The LLM freely chooses which tools to call and in what order

### Evidence

From captured proxy data (`dataset/correct_example.json` vs `dataset/wrong_example.json`):

- **Same input query** about finding source code for a SQL SELECT statement
- **Different first tool calls**:
  - Correct: `ripgrep` + `ripgrep` + `file_reader` (read model file directly)
  - Wrong: `ripgrep` + `ripgrep` + `ripgrep` (more searching, no reading)
- **Different outcomes**:
  - Correct: Found `app/models/group.rb:4399` → `get_real_followers_for_indexing_api`
  - Wrong: Explored `session_helper.rb`, `application_controller.rb` → no definitive answer

## Solution: Structured Reasoning Injection

### Core Concept

Instead of letting the LLM freely decide its approach, **inject checkpoint prompts** at specific steps that force it to:

1. Follow a consistent analysis methodology
2. Document its reasoning before acting
3. Verify findings before concluding

This is similar to "Chain of Thought" prompting but **enforced at runtime** rather than just suggested in the system prompt.

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                     ReAct Loop (Current)                        │
├─────────────────────────────────────────────────────────────────┤
│  User Query → LLM Thinks → Tool Call → Observation → Repeat     │
│                   ↑                                             │
│                   │ (LLM decides freely)                        │
└─────────────────────────────────────────────────────────────────┘

                              ↓ BECOMES ↓

┌─────────────────────────────────────────────────────────────────┐
│                  ReAct Loop (With Checkpoints)                  │
├─────────────────────────────────────────────────────────────────┤
│  User Query                                                     │
│       ↓                                                         │
│  [CHECKPOINT 1: Pattern Extraction] ← Injected prompt           │
│       ↓                                                         │
│  LLM must list: table, model, WHERE patterns, ORDER patterns    │
│       ↓                                                         │
│  Tool Calls (now guided by explicit pattern list)               │
│       ↓                                                         │
│  [CHECKPOINT 2: Results Analysis] ← Injected after searches     │
│       ↓                                                         │
│  LLM must rank matches by relevance, pick ONE to investigate    │
│       ↓                                                         │
│  File Reading (focused on single candidate)                     │
│       ↓                                                         │
│  [CHECKPOINT 3: Verification] ← Injected before answer          │
│       ↓                                                         │
│  LLM must confirm: read source, traced caller, single answer    │
│       ↓                                                         │
│  Final Answer                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Why This Reduces Non-determinism

| Without Checkpoints | With Checkpoints |
|---------------------|------------------|
| LLM picks random starting pattern | LLM must list ALL patterns first |
| May skip reading model file | Checkpoint forces model file read |
| May report "could be any of these" | Must pick ONE and verify |
| Different paths each run | Same methodology each run |

The key insight: **We're not eliminating LLM randomness, we're constraining it to a narrower decision space**.

## Implementation Plan

### Phase 1: Checkpoint Definition

Create `agent/checkpoints.py`:

```python
from dataclasses import dataclass
from typing import Optional, Callable
from enum import Enum

class CheckpointTrigger(Enum):
    """When to inject a checkpoint."""
    BEFORE_FIRST_TOOL = "before_first_tool"
    AFTER_SEARCH_RESULTS = "after_search_results"
    BEFORE_ANSWER = "before_answer"
    ON_MULTIPLE_MATCHES = "on_multiple_matches"
    ON_NO_MATCHES = "on_no_matches"

@dataclass
class Checkpoint:
    """A reasoning checkpoint to inject into the conversation."""
    name: str
    trigger: CheckpointTrigger
    prompt_template: str
    condition: Optional[Callable] = None  # Optional condition function

    def should_trigger(self, state, step_num: int) -> bool:
        """Determine if this checkpoint should fire."""
        if self.condition:
            return self.condition(state, step_num)
        return True

    def render(self, **kwargs) -> str:
        """Render the checkpoint prompt with context."""
        return self.prompt_template.format(**kwargs)
```

### Phase 2: Checkpoint Definitions for SQL Analysis

```python
SQL_ANALYSIS_CHECKPOINTS = [
    Checkpoint(
        name="pattern_extraction",
        trigger=CheckpointTrigger.BEFORE_FIRST_TOOL,
        prompt_template="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKPOINT 1: Pattern Extraction (REQUIRED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before using ANY tools, you MUST complete this checklist:

1. TABLE NAME: What table does this query target?
   → Table: ___________
   → Model: ___________ (singularized, CamelCase)
   → Model file: app/models/___________.rb

2. SQL PATTERN TYPE: Check all that apply
   □ SELECT with specific columns
   □ SELECT * (all columns)
   □ WHERE with IN clause
   □ WHERE with equality
   □ ORDER BY clause
   □ JOIN / association
   □ GROUP BY / HAVING

3. SEARCH PATTERNS: List exact regex patterns you will search:
   Pattern 1: ___________
   Pattern 2: ___________
   Pattern 3: ___________

4. FIRST ACTION: What will you do first?
   □ Read the model file (app/models/xxx.rb)
   □ Search for specific pattern
   □ Other: ___________

IMPORTANT: You MUST fill in the blanks above before proceeding.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    ),

    Checkpoint(
        name="search_results_analysis",
        trigger=CheckpointTrigger.AFTER_SEARCH_RESULTS,
        prompt_template="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKPOINT 2: Search Results Analysis (REQUIRED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

You found {num_matches} match(es). Analyze each:

| # | File | Line | Relevance (1-5) | Why? |
|---|------|------|-----------------|------|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

DECISION: Which ONE match will you investigate first?
→ Choice: ___________
→ Reason: ___________

NEXT ACTION:
□ Read the file containing this match
□ Search for callers of this method
□ Other: ___________

IMPORTANT: Pick ONE candidate. Do not investigate multiple in parallel.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
        condition=lambda state, step: state.has_search_results and state.last_match_count > 1
    ),

    Checkpoint(
        name="verification",
        trigger=CheckpointTrigger.BEFORE_ANSWER,
        prompt_template="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKPOINT 3: Verification (REQUIRED)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Before providing your final answer, confirm ALL of the following:

□ I have READ the actual source code (not just search results)
□ I found the EXACT method that generates this SQL pattern
□ I can explain WHY this code generates the SQL (column selection, ordering, etc.)
□ I traced at least ONE caller of this method
□ My answer points to a SINGLE location (file:line), not "could be any of these"

If ANY checkbox is unchecked:
→ STOP and continue investigating
→ Do NOT provide a final answer yet

If ALL checkboxes are checked:
→ Provide your answer with: file path, line number, method name, brief explanation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
        condition=lambda state, step: state.is_about_to_answer()
    ),

    Checkpoint(
        name="no_matches_recovery",
        trigger=CheckpointTrigger.ON_NO_MATCHES,
        prompt_template="""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CHECKPOINT: No Matches - Recovery Strategy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Your search returned no matches. Before trying another search:

1. ANALYZE: Why might the pattern not match?
   □ Pattern too specific (exact SQL vs Rails code)
   □ Pattern too generic (matching noise)
   □ Wrong file type filter
   □ Code might be dynamically generated

2. ALTERNATIVE APPROACHES:
   □ Search for the model name instead: `class {model_name}`
   □ Search for column names from the query
   □ Search for the WHERE clause pattern: `.where(`
   □ Use ast_grep for structural search

3. NEXT PATTERN to try: ___________
   Why this pattern: ___________
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""",
        condition=lambda state, step: state.last_match_count == 0
    )
]
```

### Phase 3: Checkpoint Injector Class

```python
# agent/checkpoint_injector.py

from typing import List, Optional
from agent.checkpoints import Checkpoint, CheckpointTrigger, SQL_ANALYSIS_CHECKPOINTS

class CheckpointInjector:
    """Manages checkpoint injection into the ReAct loop."""

    def __init__(self, checkpoints: List[Checkpoint] = None):
        self.checkpoints = checkpoints or SQL_ANALYSIS_CHECKPOINTS
        self.fired_checkpoints: set = set()  # Track which have fired

    def reset(self):
        """Reset for new query."""
        self.fired_checkpoints.clear()

    def get_checkpoint(
        self,
        trigger: CheckpointTrigger,
        state,
        step_num: int,
        **render_kwargs
    ) -> Optional[str]:
        """
        Get checkpoint prompt if one should fire.

        Args:
            trigger: The trigger event type
            state: Current agent state
            step_num: Current step number
            **render_kwargs: Variables for prompt template

        Returns:
            Checkpoint prompt string or None
        """
        for checkpoint in self.checkpoints:
            # Skip if wrong trigger
            if checkpoint.trigger != trigger:
                continue

            # Skip if already fired (each checkpoint fires once per query)
            if checkpoint.name in self.fired_checkpoints:
                continue

            # Check condition
            if not checkpoint.should_trigger(state, step_num):
                continue

            # Fire the checkpoint
            self.fired_checkpoints.add(checkpoint.name)
            return checkpoint.render(**render_kwargs)

        return None

    def inject_before_first_tool(self, state, step_num: int) -> Optional[str]:
        """Inject checkpoint before first tool call."""
        if step_num == 1:
            return self.get_checkpoint(
                CheckpointTrigger.BEFORE_FIRST_TOOL,
                state,
                step_num
            )
        return None

    def inject_after_search(
        self,
        state,
        step_num: int,
        num_matches: int
    ) -> Optional[str]:
        """Inject checkpoint after search results."""
        if num_matches == 0:
            return self.get_checkpoint(
                CheckpointTrigger.ON_NO_MATCHES,
                state,
                step_num,
                model_name=state.extracted_model_name or "Unknown"
            )
        elif num_matches > 1:
            return self.get_checkpoint(
                CheckpointTrigger.AFTER_SEARCH_RESULTS,
                state,
                step_num,
                num_matches=num_matches
            )
        return None

    def inject_before_answer(self, state, step_num: int) -> Optional[str]:
        """Inject verification checkpoint before final answer."""
        return self.get_checkpoint(
            CheckpointTrigger.BEFORE_ANSWER,
            state,
            step_num
        )
```

### Phase 4: Integration with ReactRailsAgent

Modify `agent/react_rails_agent.py`:

```python
# In __init__:
from agent.checkpoint_injector import CheckpointInjector

def __init__(self, config: Optional[AgentConfig] = None, session=None):
    # ... existing code ...
    self.checkpoint_injector = CheckpointInjector()

# In process_message (after reset):
def process_message(self, user_query: str) -> str:
    # ... existing code ...
    self.checkpoint_injector.reset()  # Reset for new query
    # ... rest of method ...

# In _process_llm_response:
def _process_llm_response(self, llm_response, messages, step_num) -> bool:
    # ... existing code for processing tool calls ...

    # === NEW: Inject checkpoints ===

    # Before first tool (step 1)
    if step_num == 1 and not llm_response.tool_calls:
        checkpoint = self.checkpoint_injector.inject_before_first_tool(
            self.state_machine.state, step_num
        )
        if checkpoint:
            self._append_to_last_user_message(messages, checkpoint)

    # After search results
    if llm_response.tool_calls:
        for tool_call in llm_response.tool_calls:
            if tool_call.name == "ripgrep":
                # Extract match count from result
                num_matches = self._extract_match_count(tool_call.result)
                checkpoint = self.checkpoint_injector.inject_after_search(
                    self.state_machine.state, step_num, num_matches
                )
                if checkpoint:
                    self._append_to_last_user_message(messages, checkpoint)

    # Before answer (when LLM seems to be concluding)
    if self._is_about_to_answer(llm_response):
        checkpoint = self.checkpoint_injector.inject_before_answer(
            self.state_machine.state, step_num
        )
        if checkpoint:
            self._append_to_last_user_message(messages, checkpoint)

    # ... rest of existing code ...

def _extract_match_count(self, result: str) -> int:
    """Extract number of matches from ripgrep result."""
    import json
    try:
        data = json.loads(result)
        return data.get("total", 0)
    except:
        return 0

def _is_about_to_answer(self, llm_response) -> bool:
    """Detect if LLM is about to provide final answer."""
    if not llm_response.text:
        return False

    # Heuristics for detecting final answer
    indicators = [
        "the source code is",
        "this sql is generated by",
        "found the source",
        "the answer is",
        "in conclusion",
        "## answer",
        "**answer**"
    ]
    text_lower = llm_response.text.lower()
    return any(ind in text_lower for ind in indicators)
```

### Phase 5: State Machine Updates

Add tracking fields to `agent/state_machine.py`:

```python
@dataclass
class ReActState:
    # ... existing fields ...

    # New fields for checkpoint support
    has_search_results: bool = False
    last_match_count: int = 0
    extracted_model_name: Optional[str] = None
    extracted_table_name: Optional[str] = None

    def record_search_result(self, num_matches: int):
        """Record search results for checkpoint logic."""
        self.has_search_results = True
        self.last_match_count = num_matches

    def is_about_to_answer(self) -> bool:
        """Check if agent appears ready to answer."""
        # Has done at least one search and one file read
        tools_used = {step.tool_name for step in self.steps if step.tool_name}
        return "ripgrep" in tools_used and "file_reader" in tools_used
```

## File Changes Summary

| File | Action | Description |
|------|--------|-------------|
| `agent/checkpoints.py` | CREATE | Checkpoint definitions and data classes |
| `agent/checkpoint_injector.py` | CREATE | Checkpoint injection logic |
| `agent/react_rails_agent.py` | MODIFY | Integrate checkpoint injector |
| `agent/state_machine.py` | MODIFY | Add search result tracking |
| `prompts/system_prompt.py` | MODIFY | Add note about checkpoint system |

## Testing Strategy

### Unit Tests

```python
# tests/test_checkpoints.py

def test_checkpoint_fires_once():
    """Each checkpoint should only fire once per query."""
    injector = CheckpointInjector()
    state = MockState(has_search_results=True, last_match_count=5)

    # First call should return prompt
    result1 = injector.inject_after_search(state, step_num=2, num_matches=5)
    assert result1 is not None
    assert "CHECKPOINT 2" in result1

    # Second call should return None (already fired)
    result2 = injector.inject_after_search(state, step_num=3, num_matches=3)
    assert result2 is None

def test_checkpoint_condition():
    """Checkpoints with conditions should respect them."""
    injector = CheckpointInjector()

    # Single match - should NOT trigger multi-match checkpoint
    state = MockState(has_search_results=True, last_match_count=1)
    result = injector.inject_after_search(state, step_num=2, num_matches=1)
    assert result is None  # No checkpoint for single match
```

### Integration Tests

```python
# tests/test_structured_reasoning.py

def test_same_query_produces_consistent_path():
    """Run same query 5 times, verify checkpoint sequence is identical."""
    query = "find source for SELECT * FROM members WHERE id IN (...)"

    checkpoint_sequences = []
    for _ in range(5):
        agent = create_test_agent()
        agent.process_message(query)

        # Extract which checkpoints fired
        sequence = list(agent.checkpoint_injector.fired_checkpoints)
        checkpoint_sequences.append(sequence)

    # All runs should have same checkpoint sequence
    assert all(seq == checkpoint_sequences[0] for seq in checkpoint_sequences)
```

## Expected Outcomes

### Before (Current Behavior)

```
Run 1: ripgrep → ripgrep → file_reader → CORRECT ANSWER
Run 2: ripgrep → ripgrep → ripgrep → WRONG PATH
Run 3: ripgrep → file_reader → ripgrep → PARTIAL ANSWER
```

### After (With Structured Reasoning)

```
Run 1: CHECKPOINT_1 → ripgrep → CHECKPOINT_2 → file_reader → CHECKPOINT_3 → CORRECT ANSWER
Run 2: CHECKPOINT_1 → ripgrep → CHECKPOINT_2 → file_reader → CHECKPOINT_3 → CORRECT ANSWER
Run 3: CHECKPOINT_1 → ripgrep → CHECKPOINT_2 → file_reader → CHECKPOINT_3 → CORRECT ANSWER
```

The checkpoints force:
1. Explicit pattern extraction (reduces random starting points)
2. Single-candidate investigation (prevents scatter-shot searching)
3. Verification before answering (prevents premature conclusions)

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Checkpoints add latency | Checkpoints are text-only, no extra API calls |
| LLM ignores checkpoint prompts | Make prompts more emphatic, add examples |
| Checkpoints too rigid for some queries | Add query-type detection, use different checkpoint sets |
| Increased token usage | Checkpoint prompts are ~200 tokens each, acceptable trade-off |

## Success Metrics

1. **Consistency**: Same query produces same answer 90%+ of the time (vs ~50% baseline)
2. **Accuracy**: Correct answer rate improves (measure against known-good dataset)
3. **Efficiency**: Average steps to answer decreases (focused investigation)
4. **User satisfaction**: Fewer "could be any of these" non-answers

## Timeline

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Checkpoint Definition | 2 hours | None |
| Phase 2: SQL Analysis Checkpoints | 2 hours | Phase 1 |
| Phase 3: Injector Class | 3 hours | Phase 1 |
| Phase 4: Agent Integration | 3 hours | Phase 3 |
| Phase 5: State Machine Updates | 1 hour | Phase 4 |
| Testing | 3 hours | All phases |
| **Total** | **14 hours** | |
