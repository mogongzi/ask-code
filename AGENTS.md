# Repository Guidelines

## Important

- **`util/` folder**: Contains utility functions and helper modules used internally by the project
- **`tools/` folder**: Contains tool definitions and implementations that can be invoked by LLMs via function calling and agent flow
- Execute `source .venv/bin/activate` before running `python3`, `python` or `pytest` commands

## Project Structure & Module Organization

- `ask_code.py` is the primary CLI for Rails-focused analysis, wiring provider selection, interactive input, and the ReAct agent loop.
- `react_rails_agent.py` contains the agent orchestration and tool wiring; `agent_tool_executor.py` mediates tool execution from agent calls.
- `streaming_client.py` manages SSE/stream rendering; conversational state and token tracking live in `chat/`.
- Context handling utilities live in `context/`; provider adapters are under `providers/`; prompt scaffolds sit in `prompts/`.
- Rendering primitives reside in `render/`, while reusable helpers and interactive shells are collected in `util/`.
- Built-in analysis tools (ripgrep, SQL analyzers, Rails inspectors) live in `tools/`; extend via subclasses of `tools.base_tool.BaseTool`.

## Build, Test, and Development Commands

- Activate the virtualenv before Python tasks: `source .venv/bin/activate`.
- Install Python dependencies with `pip install -r requirements.txt` (add `--upgrade` for refreshes).
- Launch the CLI against your proxy endpoint, e.g. `python3 ask_code.py --provider bedrock --url http://127.0.0.1:8000/invoke --project-root /path/to/rails-app`.
- Replay conversations or debug rendering using `python3 -m streaming_client < transcript.jsonl` when available.
- Run test suites via `pytest -q`; target modules with `pytest tools/test_controller_analyzer.py -q` or `pytest -k agents` for focused runs.

## Coding Style & Naming Conventions

- Python code uses 4-space indentation, snake_case functions, CapWords classes, and type hints where obvious; keep formatting Black-compatible.
- Tool modules should expose `class FooTool(BaseTool)` and register clear `name`/`description` metadata for discoverability.
- Prefer dependency injection for providers and executors so the CLI remains streaming-safe; document new tool entry points in module docstrings.

## Testing Guidelines

- Prefer `pytest` with lightweight fixtures that stub provider responses and `StreamingClient` callbacks.
- Place new tests beside the code under test or in `tests/` using the `test_*.py` pattern; cover both success and failure paths for tool contracts.
- Capture manual verification transcripts in `logs/` or dedicated markdown notes when behavior is hard to mock.

## Commit & Pull Request Guidelines

- Write commits in imperative mood with scope prefixes, e.g. `feat(tools): add migration analyzer`, `fix(chat): guard empty history`.
- PRs should describe behavior changes, include reproduction or validation steps, and note configuration updates or required environment variables.
- Attach before/after snippets or CLI transcripts when altering streaming output; flag any follow-up issues for larger refactors.

## Security & Configuration Tips

- Store API keys and OAuth secrets outside the repo (environment variables or ignored `.env` files); never log raw credentials.
- Validate proxy URLs before sharing logs and scrub tenant-specific identifiers.
- Audit new tools for filesystem or shell access and document any elevated requirements before enabling them by default.
