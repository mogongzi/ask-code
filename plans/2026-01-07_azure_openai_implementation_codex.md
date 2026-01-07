# Azure OpenAI Provider (Chat Completions via Proxy) — Implementation Plan (Codex)

## Summary

Implement the `azure` provider end-to-end against the existing local proxy endpoint (`--url` stays `http://127.0.0.1:8000/invoke`). The proxy handles routing to Azure OpenAI `chat/completions?api-version=2025-04-01-preview` and hides auth/model selection. The client side must:

- Send **blocking** (non-SSE) Chat Completions payloads by default.
- Support **tool-calling/function-calling** loops (LLM → tool_calls → execute tools → tool results back → repeat).
- Keep optional SSE support behind `--streaming` (nice-to-have; not required for your current usage).
- Treat prompt caching as **proxy/provider-managed**, with optional visibility of `cached_tokens`.

## Contract (Confirmed)

### Endpoint

- CLI keeps using `--url http://127.0.0.1:8000/invoke`
- Proxy internally routes to Azure: `chat/completions?api-version=2025-04-01-preview`

### Request (client → proxy)

- Chat Completions shape:
  - `messages: [{role, content}]`
  - `max_completion_tokens: int`
  - `tools: [{type:"function", function:{name, description, parameters}}]`
- No `model` required (proxy selects/routs model/deployment).

### Response (proxy → client)

- Chat Completions response:
  - `choices[0].message.content` (string or null)
  - `choices[0].message.tool_calls[]` with `function.name` and `function.arguments` JSON string
  - `usage.prompt_tokens`, `usage.completion_tokens`, `usage.total_tokens`
  - May include `usage.prompt_tokens_details.cached_tokens`

## Current State (Repo)

### What exists

- `providers/azure.py` already converts:
  - Anthropic-style tool messages (assistant `tool_use`, user `tool_result`) ⇄ OpenAI Chat Completions (`tool_calls`, `role:"tool"`)
  - abstract tool schemas ⇄ OpenAI `tools[]` format
- `llm/parsers/azure.py` parses `choices[0].message.content` and `choices[0].message.tool_calls`
- `tests/test_blocking_client.py` includes a basic Azure-format parsing test (uses `BlockingClient(provider=Provider.AZURE)` directly)

### What is missing / incorrect for your usage

1. `providers/azure.py` currently **always sets** `stream: true` (SSE). In blocking mode, this is wrong for your proxy contract.
2. In `ride_rails.py`, the `BlockingClient` is constructed without a provider enum, so it defaults to **Bedrock parsing**, which will not extract Azure tool calls.
3. Streaming mode for Azure (if used later) likely needs extra work:
   - `StreamingClient.send_message()` goes through the parser; today the streaming client accumulates a Bedrock-shaped synthetic response, which Azure parser will not understand unless specialized.

## Goals / Non-goals

### Goals

- Blocking Azure provider works with tools:
  - Correct payload shape (`messages`, `max_completion_tokens`, `tools`)
  - Correct tool execution loop
  - Correct usage extraction (tokens, optional cached tokens visibility)
- Minimal, surgical changes; reuse existing parser/tool wiring.

### Non-goals (for this first pass)

- Implement Azure auth, endpoint construction, deployment selection (proxy owns this).
- Implement the Responses API (different schema; would require a separate provider implementation).
- Add multimodal (images/audio).
- Guarantee prompt caching controls client-side (Azure Chat Completions does not expose Anthropic-style `cache_control`).

## Plan (Phased)

### Phase 1 — Fix Azure payload defaults (blocking-first)

**Files**
- `providers/azure.py`

**Changes**
- Add provider capability flags:
  - `supports_prompt_caching = False`
  - `supports_message_cache_control = False`
- Make `build_payload()` blocking by default:
  - Add a `stream: bool = False` kwarg (default `False`)
  - Only include `{"stream": true, "stream_options": {"include_usage": true}}` when `stream=True`
- Keep existing mapping logic:
  - assistant tool_use blocks → `tool_calls`
  - user tool_result blocks → `role:"tool"` messages
- Ensure `max_completion_tokens` is used (matches your proxy contract).
- Keep `model` optional (omit when `None` so proxy can route).

**Acceptance**
- In blocking mode, payload does **not** include `stream`.
- Unit tests assert:
  - `payload["max_completion_tokens"] == session.max_tokens`
  - `payload["tools"]` format matches OpenAI schema
  - `payload["messages"][0]` is a `system` message

### Phase 2 — Wire BlockingClient to use Azure parser in CLI

**Files**
- `ride_rails.py`

**Changes**
- When constructing `BlockingClient`, pass `provider=Provider.AZURE` if `--provider azure`.
  - There are two construction sites:
    - initial `client = create_streaming_client(...)`
    - later re-creation with tool executor in the `try:` block
- Prefer a single helper:
  - Update `create_streaming_client(use_streaming, console, provider_name)` to set:
    - `BlockingClient(provider=Provider.from_string(provider_name), ...)`
    - `StreamingClient(provider=Provider.from_string(provider_name), ...)` (optional; see Phase 5)

**Acceptance**
- Running `python3 ride_rails.py --provider azure ...` causes:
  - `BlockingClient.provider == Provider.AZURE`
  - tool calls are extracted from Azure responses and executed.

### Phase 3 — Verify tool-call loop works with Azure format

**Files**
- `agent/llm_client.py` (likely no change)
- `providers/azure.py` (only if loop issues appear)

**Notes**
- The tool loop is handled by:
  - `BaseLLMClient.send_message()` → parses tool calls → executes tools → returns `LLMResponse(tool_calls=...)`
  - `agent/llm_client.py` formats tool calls/results back into Anthropic-style blocks
  - `providers/azure.py` converts those blocks into OpenAI messages (`role:"tool"`) for the next request

**Acceptance**
- Given the sample response with `finish_reason: "tool_calls"`, the agent:
  - executes the tool(s)
  - sends follow-up request with tool results as `role:"tool"` messages
  - continues until `finish_reason: "stop"` (or no more tool calls)

### Phase 4 — Tests (unit-level, no network)

**Files**
- Update `tests/test_azure_provider.py`
- Add/extend tests where needed (prefer `pytest` style, consistent with existing tests)

**Test cases**
- `providers/azure.build_payload()`:
  - default `stream` omitted
  - `tools[]` mapping correct
  - tool-result conversion produces `role:"tool"` messages with `tool_call_id`
  - assistant tool_use conversion produces `tool_calls[]` with JSON-string `arguments`
- `ride_rails` wiring (lightweight):
  - If `create_streaming_client` is refactored to accept provider name, test that `BlockingClient.provider` is set correctly.
- Regression: ensure existing Bedrock tests still pass.

### Phase 5 (Optional) — Make Azure streaming mode coherent

Only needed if you plan to use `--streaming` with Azure.

**Goal**
- Ensure `StreamingClient.send_message()` yields a response shape that the Azure parser can handle.

**Options**
1. In `StreamingClient._make_request()`, when `self.provider == Provider.AZURE`, synthesize an Azure Chat Completions JSON response:
   - `{"choices":[{"message":{"role":"assistant","content":..., "tool_calls":[...]}}], "model":..., "usage":...}`
2. Or bypass parsers for streaming entirely by using `stream_with_live_rendering()` in the agent path (larger refactor; not recommended for first pass).

### Phase 6 (Optional) — Prompt caching visibility / hints

**Reality check**
- Azure Chat Completions doesn’t support Anthropic-style `cache_control` knobs.
- Caching, if any, is handled by Azure/provider and/or by your proxy.

**Incremental improvements**
- Display/track `usage.prompt_tokens_details.cached_tokens` when present (informational).
- If you want explicit caching control, define a **proxy-only** field (e.g. `{"proxy_cache": {"key": "...", "ttl_s": 3600}}`) and have the proxy strip it before forwarding upstream. Gate this behind an env var so unknown fields never reach Azure directly.

## Manual Verification (after implementation)

- Blocking run:
  - `python3 ride_rails.py --provider azure --url http://127.0.0.1:8000/invoke --project /path/to/rails`
- Quick tool-call sanity:
  - Ask something that reliably triggers a tool (e.g., “search for controller UsersController”).
  - Confirm tool execution occurs and the agent continues with tool results.

## Follow-ups

- Add a separate `openai_responses` provider if you later want the Responses API.
- Consider normalizing usage (cost/pricing) per model if you care about cost reporting; otherwise keep token-only.

