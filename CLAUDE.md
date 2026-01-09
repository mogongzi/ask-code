# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important

- **`util/` folder**: Contains utility functions and helper modules used internally by the project
- **`tools/` folder**: Contains tool definitions and implementations that can be invoked by LLMs via function calling and agent flow
- **`tests/` folder**: Contains all test files (unit tests, integration tests, test utilities)
- Execute `source .venv/bin/activate` before running `python3`, `python` or `pytest` commands

**Keep in root directory only:**
- `README.md` - Project overview and quick start
- `CLAUDE.md` - This file (instructions for Claude Code)
- `AGENTS.md` - Agent architecture overview


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
- **`agent/react_rails_agent.py`**: ReAct pattern implementation for intelligent Rails codebase analysis
- **`agent/state_machine.py`**: ReAct state tracking (THOUGHT/ACTION/OBSERVATION cycles)
- **`agent/tool_registry.py`**: Tool registration and schema generation for LLM function calling
- **`llm/clients/streaming.py`**: SSE client for handling LLM streaming responses with tool execution
- **`llm/clients/blocking.py`**: Blocking/synchronous client for single request/response with spinner animation
- **`agent_tool_executor.py`**: Bridges between LLM function calls and agent tools

**Tool System:**

- **`tools/base_tool.py`**: Abstract base class for all analysis tools
- **`tools/ripgrep_tool.py`**: Fast text/pattern search using ripgrep
- **`tools/file_reader_tool.py`**: Read file contents with line numbers
- **`tools/directory_tool.py`**: List and explore directory structure
- **`tools/ast_grep_tool.py`**: AST-based code pattern search

**Support Modules:**

- **`agent/`**: ReAct agent core (`react_rails_agent.py`, `state_machine.py`, `tool_registry.py`, `response_analyzer.py`, `llm_client.py`, `config.py`)
- **`llm/`**: LLM infrastructure (`clients/` for streaming/blocking, `parsers/` for response parsing, `types.py`, `error_handling.py`)
- **`chat/`**: Session orchestration (`session.py`, `conversation.py`), usage tracking, tool workflow management
- **`render/`**: Live markdown rendering (`markdown_live.py`, `block_buffered.py`)
- **`providers/`**: LLM provider adapters (`azure.py`, `bedrock.py`)
- **`util/`**: Input helpers, path browser, command handlers, URL helpers
- **`prompts/`**: System prompts for the ReAct agent

**ReAct Agent Flow:**

1. User submits query via CLI
2. `ReactRailsAgent.process_message()` initializes the ReAct loop
3. Loop execution (`_execute_react_loop`):
   - Agent calls LLM with available tool schemas
   - LLM returns reasoning text (THOUGHT) and/or tool calls (ACTION)
   - Tools execute via `AgentToolExecutor` and return results (OBSERVATION)
   - `ResponseAnalyzer` determines if answer is complete
4. Loop continues until a stopping condition is met:
   - LLM provides substantive answer (>200 chars without tool calls)
   - Max steps reached (default: 100)
   - Agent stuck (2+ consecutive steps without tool calls)
   - Infinite loop detected (same exact action repeated 3+ times)
5. Final response is returned and rendered with optional reasoning trail

**Available Tools:**
- `ripgrep` - Fast text/pattern search across codebase
- `file_reader` - Read file contents with line numbers
- `list_directory` - Explore directory structure
- `ast_grep` - AST-based code pattern search

## CLI Usage

- `/think`: Toggle reasoning mode on/off
- `/reasoning`: Display the reasoning trail from last query
- `/status`: Show current session status and token usage
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
