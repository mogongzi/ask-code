# Bug: ReAct Trace Omits Parallel Tool Calls (ast_grep missing)

**Date:** 2026-01-04
**Status:** Documented, not yet fixed
**Severity:** Medium (display bug, does not affect agent functionality)

## Problem Summary

The ReAct Trace display omits tool calls when the LLM makes multiple parallel tool calls in a single response. Only the first tool call is shown; subsequent parallel calls (like `ast_grep`) are silently dropped.

## Observed Behavior

User ran a query and saw this trace:
```
Step 1: ripgrep (IDs search)
Step 2: ripgrep (Member.where patterns)
Step 3: ripgrep (.where.order patterns)
Step 4: file_reader (group.rb)
Step 5: ripgrep (.order(id: :asc))
Step 6: file_reader (group.rb)
Step 7: ripgrep (get_real_followers_for_indexing_api)
Step 8: Final answer
```

But the actual API request/response showed the LLM made **additional ast_grep calls** that were not displayed:
- `ast_grep` for `Member.where(id: $_).order`
- `ast_grep` for `Member.$_($$).where(id: $_).order`
- `ast_grep` for `$_.where(id: $_).order(id: :asc)`

## Root Cause

**File:** `agent/state_machine.py`
**Method:** `get_complete_reasoning_trail()` (lines 385-417)

The algorithm assumes a sequential pattern:
```
THOUGHT → ACTION → OBSERVATION → THOUGHT → ACTION → OBSERVATION
```

But Claude can call **multiple tools in parallel**, creating:
```
THOUGHT → ACTION → ACTION → ACTION → OBSERVATION → OBSERVATION → OBSERVATION
```

### Buggy Code

```python
def get_complete_reasoning_trail(self) -> List[Dict[str, Any]]:
    cycles = []
    i = 0
    while i < len(self.steps):
        step = self.steps[i]
        if step.step_type == StepType.THOUGHT:
            cycle = {"thought": step.content}
            next_idx = i + 1
            # Look for following ACTION - ONLY FINDS FIRST ONE
            if next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.ACTION:
                action = self.steps[next_idx]
                cycle["tool_name"] = action.tool_name
                cycle["tool_input"] = action.tool_input
                next_idx += 1
                # Look for following OBSERVATION - EXPECTS IT IMMEDIATELY AFTER
                # But with parallel calls, there are more ACTIONs here!
                if next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.OBSERVATION:
                    obs = self.steps[next_idx]
                    cycle["tool_output"] = obs.content
                    next_idx += 1
            cycles.append(cycle)
            i = next_idx
        else:
            i += 1  # Orphaned ACTIONs are skipped here!
    return cycles
```

### What Happens

1. Finds THOUGHT at index 0
2. Finds first ACTION (ripgrep) at index 1
3. Looks for OBSERVATION at index 2 - but finds second ACTION (ast_grep)!
4. No observation found for this cycle
5. Moves to index 2 (the ast_grep ACTION)
6. ast_grep ACTION has no preceding THOUGHT, so `else` branch skips it
7. All parallel tool calls except the first are lost

## Proposed Fix

Modify `get_complete_reasoning_trail()` to handle multiple ACTIONs per THOUGHT:

```python
def get_complete_reasoning_trail(self) -> List[Dict[str, Any]]:
    """
    Get complete ReAct cycles with thought, action(s), and observation(s).

    Handles parallel tool calls by collecting ALL consecutive ACTIONs
    and their corresponding OBSERVATIONs into a single cycle.
    """
    cycles = []
    i = 0
    while i < len(self.steps):
        step = self.steps[i]
        if step.step_type == StepType.THOUGHT:
            cycle = {
                "thought": step.content,
                "tools": []  # List of {tool_name, tool_input, tool_output}
            }
            next_idx = i + 1

            # Collect ALL consecutive ACTIONs
            actions = []
            while next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.ACTION:
                actions.append(self.steps[next_idx])
                next_idx += 1

            # Collect ALL consecutive OBSERVATIONs
            observations = []
            while next_idx < len(self.steps) and self.steps[next_idx].step_type == StepType.OBSERVATION:
                observations.append(self.steps[next_idx])
                next_idx += 1

            # Pair actions with observations (by order)
            for j, action in enumerate(actions):
                tool_info = {
                    "tool_name": action.tool_name,
                    "tool_input": action.tool_input,
                    "tool_output": observations[j].content if j < len(observations) else None
                }
                cycle["tools"].append(tool_info)

            # For backward compatibility, also set first tool as top-level fields
            if cycle["tools"]:
                first_tool = cycle["tools"][0]
                cycle["tool_name"] = first_tool["tool_name"]
                cycle["tool_input"] = first_tool["tool_input"]
                cycle["tool_output"] = first_tool["tool_output"]

            cycles.append(cycle)
            i = next_idx
        else:
            i += 1
    return cycles
```

## Files to Modify

1. **`agent/state_machine.py`** - Fix `get_complete_reasoning_trail()` method
2. **`agent/reasoning_display.py`** - Update `format_complete_reasoning_section()` to display multiple tools per cycle
3. **`agent/hooks.py`** - If `ReasoningTrailHook.get_complete_reasoning_trail()` has similar logic, fix it too
4. **`tests/test_reasoning_display.py`** - Add test for parallel tool calls

## Display Format Options

### Option A: Expand each parallel tool as sub-step
```
▸ Step 3: I need to search for patterns...
  Tool: ripgrep
  Input: {"pattern": "..."}
  Output: {...}

  Tool: ast_grep
  Input: {"pattern": "..."}
  Output: {...}
```

### Option B: Show count with expandable details
```
▸ Step 3: I need to search for patterns...
  Tools: ripgrep, ast_grep, ast_grep (3 parallel calls)
  ...
```

## Testing

1. Create a test case with multiple parallel tool calls in steps list
2. Verify all tools appear in the reasoning trail
3. Verify display renders all tools correctly

## Notes

- This is a **display-only bug** - the agent actually executes all tool calls correctly
- The state machine records all steps properly (verified by checking `self.steps`)
- Only the trail extraction/display logic is broken
