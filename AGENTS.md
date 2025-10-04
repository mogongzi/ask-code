# Repository Guidelines

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
- `CLAUDE.md` - Instructions for Claude Code AI agent
- `AGENTS.md` - This file (agent architecture and development guidelines)

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

## Project Structure & Module Organization

- `ride_rails.py` is the primary CLI for Rails-focused analysis, wiring provider selection, interactive input, and the ReAct agent loop.
- `react_rails_agent.py` contains the agent orchestration and tool wiring; `agent_tool_executor.py` mediates tool execution from agent calls.
- `streaming_client.py` manages SSE/stream rendering; `blocking_client.py` handles synchronous single-request responses with spinner animation.
- Conversational state and token tracking live in `chat/`.
- Context handling utilities live in `context/`; provider adapters are under `providers/`; prompt scaffolds sit in `prompts/`.
- Rendering primitives reside in `render/`, while reusable helpers and interactive shells are collected in `util/`.
- Built-in analysis tools (ripgrep, SQL analyzers, Rails inspectors) live in `tools/`; extend via subclasses of `tools.base_tool.BaseTool`.

## Build, Test, and Development Commands

- Activate the virtualenv before Python tasks: `source .venv/bin/activate`.
- Install Python dependencies with `pip install -r requirements.txt` (add `--upgrade` for refreshes).
- Launch the CLI against your proxy endpoint, e.g. `python3 ride_rails.py --provider bedrock --url http://127.0.0.1:8000/invoke --project-root /path/to/rails-app`.
- Replay conversations or debug rendering using `python3 -m streaming_client < transcript.jsonl` when available.
- Run test suites via `pytest -q`; target modules with `pytest tools/test_controller_analyzer.py -q` or `pytest -k agents` for focused runs.

## Coding Style & Naming Conventions

- Python code uses 4-space indentation, snake_case functions, CapWords classes, and type hints where obvious; keep formatting Black-compatible.
- Tool modules should expose `class FooTool(BaseTool)` and register clear `name`/`description` metadata for discoverability.
- Prefer dependency injection for providers and executors so the CLI remains streaming-safe; document new tool entry points in module docstrings.

## Testing Guidelines

**Test File Organization:**
- **IMPORTANT**: All test files MUST be placed in the `tests/` directory
- Test files must follow naming convention: `test_*.py`
- Never create test files in the root directory

**Test Framework:**
- Prefer `pytest` with lightweight fixtures that stub provider responses and `StreamingClient` callbacks
- Use `tests/conftest.py` for shared fixtures and configuration
- Run tests: `pytest tests/` or `python tests/run_tests.py`

**Test Coverage:**
- Cover both success and failure paths for tool contracts
- Unit tests: `tests/test_<module_name>.py`
- Integration tests: `tests/test_<feature_name>.py`
- Capture manual verification transcripts in `journal/` when behavior is hard to mock

**Examples:**
```bash
# ✅ Correct
tests/test_spinner_animation.py
tests/test_non_streaming.py
tests/test_agent_config.py

# ❌ Wrong (never in root)
test_my_feature.py
```

## Architecture Overview

This is a Rails code analysis tool using a ReAct (Reasoning + Acting) AI agent architecture:

**Core Components:**

- **`ride_rails.py`**: Main CLI entry point for Rails code analysis with ReAct agent
- **`agent/react_rails_agent.py`**: ReAct pattern implementation for intelligent Rails codebase analysis
- **`streaming_client.py`**: SSE client for handling LLM streaming responses with tool execution
- **`blocking_client.py`**: Blocking/synchronous client for single request/response with spinner animation
- **`agent_tool_executor.py`**: Bridges between LLM function calls and agent tools

**Tool System:**

- **`tools/base_tool.py`**: Abstract base class for all analysis tools
- **`tools/transaction_analyzer.py`**: Analyzes complete SQL transaction logs to identify Rails patterns and callback chains
- **Rails-specific tools**: `model_analyzer.py`, `controller_analyzer.py`, `route_analyzer.py`, `migration_analyzer.py`
- **Search tools**: `ripgrep_tool.py`, `ast_grep_tool.py`, `ctags_tool.py`, `enhanced_sql_rails_search.py`

**Support Modules:**

- **`agent/`**: ReAct agent components (state machine, response analyzer, LLM client, tool registry, configuration)
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

**Interactive Commands:**
- `/think`: Toggle reasoning mode on/off
- `/clear`: Clear conversation history
- `/status`: Show agent status and configuration
- `/help`: Show available commands

**Input Methods:**
- Multi-line input: Use Ctrl+J for new lines, Enter to submit
- Escape or Ctrl+C to cancel during streaming
- Up/Down arrows: Navigate input history

**Running the Application:**
- Main CLI: `python3 ride_rails.py --project /path/to/rails/project`
- Default endpoint: `http://127.0.0.1:8000/invoke` (blocking mode)
- Provider options: `--provider bedrock` or `--provider azure`
- Client modes: `--streaming` for SSE streaming (default: blocking)

## Verbose Mode

Use the `--verbose` flag to enable detailed tool execution logging and error traces (INFO and DEBUG levels):

```bash
python3 ride_rails.py --project /path/to/rails/project --verbose
```

**Verbose mode provides:**
- Detailed agent step tracking and decision logging
- Tool execution traces and performance metrics
- LLM request/response debugging information
- State machine transitions and loop detection warnings

**Default mode** (without `--verbose`) shows only WARNING and ERROR level logs for a clean user experience.

## Commit & Pull Request Guidelines

- Write commits in imperative mood with scope prefixes, e.g. `feat(tools): add migration analyzer`, `fix(chat): guard empty history`.
- PRs should describe behavior changes, include reproduction or validation steps, and note configuration updates or required environment variables.
- Attach before/after snippets or CLI transcripts when altering streaming output; flag any follow-up issues for larger refactors.

## Security & Configuration Tips

- Store API keys and OAuth secrets outside the repo (environment variables or ignored `.env` files); never log raw credentials.
- Validate proxy URLs before sharing logs and scrub tenant-specific identifiers.
- Audit new tools for filesystem or shell access and document any elevated requirements before enabling them by default.
