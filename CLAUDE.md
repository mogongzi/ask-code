# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Important

- **`util/` folder**: Contains utility functions and helper modules used internally by the project
- **`tools/` folder**: Contains tool definitions and implementations that can be invoked by LLMs via function calling and agent flow
- Execute `source .venv/bin/activate` before running `python3`, `python` or `pytest` commands

## Development Commands

**Prerequisites:**

- Python 3.13+
- Virtual environment: `python3 -m venv .venv && source .venv/bin/activate`

**Running the Application:**

- Main Rails analysis CLI: `python3 ask_code.py --project /path/to/rails/project`
- Default endpoint: `http://127.0.0.1:8000/invoke`
- Provider options: `--provider bedrock` or `--provider azure`

**Installation:**

- Install dependencies: `pip install -r requirements.txt`
- Required packages: `rich>=13.0.0`, `requests>=2.28.0`, `prompt-toolkit>=3.0.0`, `sqlglot>=10.0.0`

**Testing:**

- Tests should use pytest framework
- No existing test files found in project structure
- Create tests in a `tests/` directory if needed

## Architecture Overview

This is a Rails code analysis tool using a ReAct (Reasoning + Acting) AI agent architecture:

**Core Components:**

- **`ask_code.py`**: Main CLI entry point for Rails code analysis with ReAct agent
- **`react_rails_agent.py`**: ReAct pattern implementation for intelligent Rails codebase analysis
- **`streaming_client.py`**: SSE client for handling LLM streaming responses with tool execution
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

## Debug Mode

Set `AGENT_TOOL_DEBUG=1` environment variable to enable detailed tool execution logging.
