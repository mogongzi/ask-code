# Repository Guidelines

## Project Structure & Module Organization
`ride_rails.py` drives the CLI and ReAct loop; supporting agent wiring lives in `agent/` and `agent_tool_executor.py`. Shared state management sits in `chat/`, provider adapters in `providers/`, prompts in `prompts/`, and rendering helpers in `render/`. Place reusable utilities under `util/`, while analysis tools reside in `tools/` and extend `tools.base_tool.BaseTool`. Keep documentation that is not this guide inside `journal/` using the `YYYY-MM-DD_TOPIC.md` pattern. Tests belong exclusively in `tests/` alongside fixtures and helpers.

### SQL Log Pre‑Processing (Adaptive Extractor)
- `util/sql_log_extractor.py` provides an adaptive extractor that normalizes SQL from heterogeneous DB logs (MySQL general log, multi‑line statements, header‑only entries like `... Query\nSELECT ...`).
- It detects transaction boundaries (`BEGIN`, `START TRANSACTION`, `COMMIT`, `ROLLBACK`), accumulates multi‑line statements, strips comments for typing, and preserves metadata.
- Downstream tools consume the normalized SQL to improve robustness and accuracy.

## Build, Test, and Development Commands
Activate the virtualenv with `source .venv/bin/activate` before running Python commands. Install dependencies via `pip install -r requirements.txt`. Launch the CLI locally with `python3 ride_rails.py --provider bedrock --url http://127.0.0.1:8000/invoke --project-root /path/to/rails-app`. Replay saved transcripts using `python3 -m streaming_client < transcript.jsonl`. Run the full test suite with `pytest -q`; target a module by running `pytest tools/test_controller_analyzer.py -q` or filter with `pytest -k agents`.

### Tooling Updates (SQL)
- `tools/enhanced_sql_rails_search.py` now pre‑processes input with the adaptive extractor:
  - If multiple statements or a transaction block are detected, it returns a hint to use `transaction_analyzer` with a detected query count.
  - If exactly one statement is detected, it analyzes the normalized SQL.
- `tools/transaction_analyzer.py` consumes the adaptive extractor output to build a transaction flow:
  - Recognizes `START TRANSACTION` as `BEGIN`.
  - Splits transaction blocks into individual statements for timeline/patterns.
  - Extracts controller/action from MySQL comments like `/* controller:Foo, action:bar */`.

## Coding Style & Naming Conventions
Use Python 3 syntax with 4-space indentation, snake_case functions, CapWords classes, and type hints when obvious. Keep code Black-compatible even if Black is not enforced. Tool classes must expose explicit `name` and `description` metadata. Prefer dependency injection for providers, executors, and renderers so the agent remains streaming-safe. Keep Markdown ASCII unless the file already uses other characters.

## Testing Guidelines
Write tests with `pytest` and keep filenames in the form `tests/test_*.py`. Cover success and failure paths for each tool, including error handling in executor bridges. Use `tests/conftest.py` for shared fixtures, and capture manual verification notes in `journal/` rather than the root. When adding new analyzers, test both the tool output and the agent dispatch behavior.

### SQL Tests Added
- `tests/test_sql_log_extractor.py`: Validates multi‑line extraction and transaction boundary handling.
- `tests/test_transaction_analyzer_log_parsing.py`: Ensures `SELECT`/`COMMIT` and base table detection (e.g., `customers`) from real‑world log shape.
- `tests/test_enhanced_search_preproc.py`: Verifies `enhanced_sql_rails_search` redirects transaction‑like input to `transaction_analyzer`.

## Commit & Pull Request Guidelines
Commits follow imperative mood with scope prefixes, e.g., `feat(tools): add migration analyzer` or `fix(chat): guard empty history`. Pull requests should describe behavior changes, include validation steps or transcripts, and link issues when relevant. Mention configuration or environment updates explicitly. Provide before/after snippets for user-facing output changes and highlight follow-up work if needed.

## Security & Configuration Tips
Store credentials outside the repository and avoid logging secrets. Validate proxy URLs before sharing transcripts. Document any tool that shells out or touches the filesystem, and call out elevated requirements before enabling it by default.
