# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important

- **`util/` folder**: Contains utility functions and helper modules used internally by the project
- **`tools/` folder**: Contains tool definitions and implementations that can be invoked by LLMs via function calling and agent flow
- **`journal/` folder**: Contains development documentation, implementation notes, and technical journals
- **`tests/` folder**: Contains all test files (unit tests, integration tests, test utilities)
- Execute `source .venv/bin/activate` before running `python3`, `python` or `pytest` commands

## Documentation Policy

**IMPORTANT**: All markdown documentation created by coding agents (Claude, Codex, or others) MUST be placed in the `journal/` folder.

**Keep in root directory only:**
- `README.md` - Project overview and quick start
- `CLAUDE.md` - This file (instructions for Claude Code)
- `AGENTS.md` - Agent architecture overview

**Place in journal/ folder:**
- Implementation notes and detailed technical documentation
- Bug fix summaries and troubleshooting guides
- Feature development journals and progress logs
- API documentation and architectural deep-dives
- Testing documentation and debugging guides
- Any other development-related markdown files

**Naming Convention:**
- Use timestamp prefix: `YYYY-MM-DD_TOPIC.md`
- Today's date: Use the actual date from the system
- Example: `2025-09-30_NEW_FEATURE.md`

**Examples:**
```bash
# ✅ Correct placement and naming
journal/2025-09-30_FIXES_SUMMARY.md
journal/2025-09-30_NON_STREAMING_API.md
journal/2025-09-30_SPINNER_ANIMATION.md
journal/2025-09-30_AGENT_FLOW_DETAILED.md

# ❌ Wrong placement (do not create these in root)
FEATURE_NOTES.md
BUG_FIXES.md
IMPLEMENTATION_DETAILS.md

# ❌ Wrong naming (missing timestamp)
journal/FEATURE_NOTES.md
journal/BUG_FIXES.md
```

## Test File Policy

**IMPORTANT**: All test files MUST be placed in the `tests/` directory.

**Naming Convention:**
- All test files must start with `test_` prefix
- Format: `test_<module_name>.py` or `test_<feature>.py`
- Example: `test_spinner_animation.py`, `test_non_streaming.py`

**Examples:**
```bash
# ✅ Correct placement
tests/test_spinner_animation.py
tests/test_non_streaming.py
tests/test_agent_config.py
tests/test_base_tool.py

# ❌ Wrong placement (do not create test files in root)
test_my_feature.py
test_new_functionality.py

# ❌ Wrong naming (must start with test_)
tests/my_feature_test.py
tests/feature_tests.py
```

**Test Organization:**
- Unit tests: `tests/test_<module_name>.py`
- Integration tests: `tests/test_<feature_name>.py`
- Test fixtures: `tests/conftest.py`
- Test utilities: `tests/run_tests.py`
```

## Development Commands

**Prerequisites:**

- Python 3.13+
- Virtual environment: `python3 -m venv .venv && source .venv/bin/activate`

**Running the Application:**

- Main Rails analysis CLI: `python3 ride_rails.py --project /path/to/rails/project`
- Default endpoint: `http://127.0.0.1:8000/invoke` (blocking mode)
- Provider options: `--provider bedrock` or `--provider azure`
- Client modes: `--streaming` for SSE streaming (default: blocking)

**Installation:**

- Install dependencies: `pip install -r requirements.txt`
- Required packages: `rich>=13.0.0`, `requests>=2.28.0`, `prompt-toolkit>=3.0.0`, `sqlglot>=10.0.0`

**Testing:**

- All test files must be placed in the `tests/` directory
- Test files should follow naming convention: `test_*.py`
- Use pytest framework for all tests
- Run tests: `pytest tests/` or `python tests/run_tests.py`
- Test utilities: `tests/conftest.py` for fixtures and configuration

## Architecture Overview

This is a Rails code analysis tool using a ReAct (Reasoning + Acting) AI agent architecture:

**Core Components:**

- **`ride_rails.py`**: Main CLI entry point for Rails code analysis with ReAct agent
- **`react_rails_agent.py`**: ReAct pattern implementation for intelligent Rails codebase analysis
- **`streaming_client.py`**: SSE client for handling LLM streaming responses with tool execution
- **`blocking_client.py`**: Blocking/synchronous client for single request/response with spinner animation
- **`agent_tool_executor.py`**: Bridges between LLM function calls and agent tools

**Tool System:**

- **`tools/base_tool.py`**: Abstract base class for all analysis tools
- **`tools/transaction_analyzer.py`**: Analyzes complete SQL transaction logs to identify Rails patterns and callback chains
- **Rail-specific tools**: `model_analyzer.py`, `controller_analyzer.py`, `route_analyzer.py`, `migration_analyzer.py`
- **Search tools**: `ripgrep_tool.py`, `ast_grep_tool.py`, `ctags_tool.py`, `enhanced_sql_rails_search.py`

**Support Modules:**

- **`chat/`**: Session orchestration (`session.py`, `conversation.py`), usage tracking, tool workflow management
- **`render/`**: Live markdown rendering (`markdown_live.py`, `block_buffered.py`)
- **`providers/`**: LLM provider adapters (`azure.py`, `bedrock.py`)
- **`util/`**: Input helpers, path browser, command handlers, URL helpers
- **`prompts/`**: System prompts for the ReAct agent

**ReAct Agent Flow:**

1. User submits Rails-related query (including SQL transaction logs)
2. Agent detects query type and selects appropriate tools:
   - Single SQL queries → `enhanced_sql_rails_search`
   - Transaction logs → `transaction_analyzer` (automatically detects multi-query logs)
   - Model/controller analysis → specific analyzer tools
3. Tools execute analysis on the Rails codebase
4. Agent observes tool results and decides next action
5. Process repeats until final answer is formulated

**Transaction Analysis Feature:**

The agent now automatically detects SQL transaction logs (multiple queries with timestamps) and uses the specialized `transaction_analyzer` tool to:

- Parse complete transaction flows from BEGIN to COMMIT
- Identify Rails callback chains and triggers
- Map database operations to likely Rails patterns (audit logging, feed generation, etc.)
- Provide source code search across the entire transaction context

## CLI Usage

- `/think`: Toggle reasoning mode on/off
- `/clear`: Clear conversation history
- `/help`: Show available commands
- Multi-line input: Use Ctrl+J for new lines, Enter to submit
- Escape or Ctrl+C to cancel during streaming

## Verbose Mode

Use the `--verbose` flag to enable detailed tool execution logging and error traces (INFO and DEBUG levels):

```bash
python3 ride_rails.py --project /path/to/rails/project --verbose
```

By default, only WARNING and ERROR level logs are shown.
