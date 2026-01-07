# Implementation Plan: "Explored" Feature for ride_rails.py

## Goal

Implement Codex-style "Explored" tracking and display in ride_rails.py, showing:
```
• Explored
  └ Search FROM `members` WHERE `members`.`id` IN in .
    Search default_scope in member.rb
    Read action_item.rb, expert_tag.rb, feed_filter.rb
    List ls -la
```

---

## Files to Create

### 1. `agent/exploration_tracker.py` (NEW)

Core tracking model - equivalent to Codex's ExecCell.

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional
import time

class ExploredType(Enum):
    READ = "Read"
    LIST = "List"
    SEARCH = "Search"

@dataclass
class ExploredItem:
    type: ExploredType
    query: Optional[str] = None  # For Search: the pattern
    path: Optional[str] = None   # Directory or file path
    names: List[str] = field(default_factory=list)  # For Read: file names
    timestamp: float = field(default_factory=time.time)

@dataclass
class ExplorationTracker:
    items: List[ExploredItem] = field(default_factory=list)
    is_active: bool = False

    def add_search(self, query: str, path: str = ".")
    def add_read(self, file_names: List[str])
    def add_list(self, path: str)
    def clear(self)
    def get_grouped_items(self) -> List[ExploredItem]  # Groups consecutive Reads
```

### 2. `render/explored_display.py` (NEW)

Rich-based rendering for the "Explored" section.

```python
from rich.console import Console
from rich.text import Text
from rich.live import Live
from typing import List

class ExploredDisplay:
    def __init__(self, console: Console):
        self.console = console

    def render(self, tracker: ExplorationTracker) -> None:
        """Render the Explored section with tree structure."""
        # Header: • Explored (or ◦ Exploring with spinner)
        # Items with └ prefix for first, spaces for rest
        # Grouping: consecutive Reads → single line with comma-separated names
```

---

## Files to Modify

### 3. `agent/state_machine.py`

**Add exploration tracking to ReActState:**

```python
# Line ~76, add to ReActState class:
from agent.exploration_tracker import ExplorationTracker

@dataclass
class ReActState:
    # ... existing fields ...
    exploration: ExplorationTracker = field(default_factory=ExplorationTracker)
```

**Add methods:**
- `record_exploration(type, query, path, names)` - Called when exploration tool executes

### 4. `agent/react_rails_agent.py`

**Hook into tool execution (around line 285-295):**

```python
# After tool execution, classify and record exploration
def _record_exploration_from_tool(self, tool_name: str, tool_input: dict, tool_output: any):
    """Classify tool call and record to exploration tracker."""
    if tool_name in ["ripgrep", "grep", "search"]:
        self.state_machine.state.exploration.add_search(
            query=tool_input.get("pattern", ""),
            path=tool_input.get("path", ".")
        )
    elif tool_name in ["file_reader", "read_file"]:
        self.state_machine.state.exploration.add_read(
            file_names=[tool_input.get("file_path", "").split("/")[-1]]
        )
    elif tool_name in ["list_directory", "ls"]:
        self.state_machine.state.exploration.add_list(
            path=tool_input.get("path", ".")
        )
```

**Display exploration before/after processing:**
- Call `ExploredDisplay.render()` after each tool execution
- Or render once at end of ReAct loop

### 5. `ride_rails.py`

**Add explored display integration (around line 358-364):**

```python
# After agent processing, show explored summary
from render.explored_display import ExploredDisplay

explored_display = ExploredDisplay(console)
# Show during processing or at completion
```

### 6. `tools/base_tool.py` (Optional Enhancement)

**Add exploration metadata to tool results:**

```python
@dataclass
class ToolResult:
    success: bool
    content: Any
    exploration_type: Optional[ExploredType] = None
    exploration_details: Optional[dict] = None
```

---

## Implementation Steps

### Step 1: Create Data Model
1. Create `agent/exploration_tracker.py`
2. Define `ExploredType` enum, `ExploredItem` dataclass, `ExplorationTracker` class
3. Implement grouping logic for consecutive Reads

### Step 2: Create Renderer
1. Create `render/explored_display.py`
2. Implement Rich-based tree rendering with:
   - `•` bullet prefix
   - `└` for first item, spaces for subsequent
   - Cyan-colored operation types (Search, Read, List)
   - Query/path formatting

### Step 3: Integrate with State Machine
1. Add `exploration: ExplorationTracker` to `ReActState`
2. Add `record_exploration()` method
3. Add `clear_exploration()` for `/clear` command

### Step 4: Hook Tool Execution
1. In `react_rails_agent.py`, classify tool calls by type
2. Record to exploration tracker after each tool execution
3. Map tool names to ExploredType:
   - `ripgrep`, `grep`, `search`, `enhanced_sql_rails_search` → SEARCH
   - `file_reader`, `read_file`, `model_analyzer`, `controller_analyzer` → READ
   - `list_directory` → LIST

### Step 5: Display Integration
1. Add exploration display to REPL loop in `ride_rails.py`
2. Show "Exploring" with spinner during active exploration
3. Show "Explored" with bullet when complete
4. Clear exploration on `/clear` command

### Step 6: Testing
1. Create `tests/test_exploration_tracker.py`
2. Test grouping logic for consecutive Reads
3. Test rendering output format
4. Integration test with mock tool calls

---

## Visual Specification

**Display Mode: Live Updates**
- Show "Exploring" with spinner as tools execute
- Update the display after each tool completes
- Transition to "Explored" with solid bullet when query processing completes

**During exploration (active):**
```
◦ Exploring
  └ Search pattern in path
    Read file1.rb
```

**After exploration (complete):**
```
• Explored
  └ Search FROM `members` WHERE `members`.`id` IN in .
    Search default_scope in member.rb
    Search select\( in member.rb
    List ls -la
    Search 290118|10719030|19102494 in log
    Read action_item.rb, expert_tag.rb, feed_filter.rb, member_mentions.rb
    Search \bMember\.find\( in app
```

**Implementation for Live Updates:**
- Use Rich's `Live` context manager for in-place updates
- Re-render the entire "Explored" section on each tool completion
- Transition from `◦ Exploring` to `• Explored` when `is_active` becomes False

**Key formatting rules:**
1. Header: `•` or `◦` + space + "Explored"/"Exploring" (bold)
2. First item: `  └ ` prefix (2 spaces + └ + space)
3. Subsequent items: `    ` prefix (4 spaces)
4. Operation type: Cyan colored ("Search", "Read", "List")
5. Search format: `Search {query} in {path}`
6. Read format: `Read {name1}, {name2}, ...` (grouped)
7. List format: `List {path or command}`

---

## Key Files Summary

| File | Action | Purpose |
|------|--------|---------|
| `agent/exploration_tracker.py` | CREATE | Data model for tracking |
| `render/explored_display.py` | CREATE | Rich-based rendering |
| `agent/state_machine.py` | MODIFY | Add exploration field |
| `agent/react_rails_agent.py` | MODIFY | Hook tool execution |
| `ride_rails.py` | MODIFY | Display integration |
| `tests/test_exploration_tracker.py` | CREATE | Unit tests |

---

## Tool Name Mapping

| Tool Class | ExploredType | Display |
|------------|--------------|---------|
| `ripgrep_tool.py` | SEARCH | `Search {pattern} in {path}` |
| `enhanced_sql_rails_search.py` | SEARCH | `Search {query} in {scope}` |
| `file_reader_tool.py` | READ | `Read {filename}` |
| `model_analyzer.py` | READ | `Read {model}.rb` |
| `controller_analyzer.py` | READ | `Read {controller}.rb` |
| Directory listing tools | LIST | `List {path}` |

---

## Reference: Codex Implementation

Key files from Codex for reference:
- `codex-rs/tui/src/exec_cell/model.rs` - ExecCell/ExecCall structs
- `codex-rs/tui/src/exec_cell/render.rs` - `exploring_display_lines()` method
- `codex-rs/core/src/parse_command.rs` - ParsedCommand enum
