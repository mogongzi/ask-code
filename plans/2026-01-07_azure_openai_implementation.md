# Azure OpenAI Provider Implementation Plan

## Current State Analysis

### What's Already Implemented
The `providers/azure.py` file has significant implementation:
- `build_payload()` - Constructs OpenAI-compatible payloads with proper message/tool format conversion
- `map_events()` - Parses OpenAI SSE streaming format into unified events
- `_build_openai_tools()` - Converts abstract tool format to OpenAI function format
- `_build_openai_messages()` - Handles message format conversion (tool_use, tool_result)
- Token estimation fallback when usage data is missing

### Gap Analysis
The current implementation is **payload/parsing complete** but missing **HTTP transport layer integration**:

1. **No Authentication** - Azure OpenAI requires API key or Azure AD token
2. **No Header Configuration** - Provider doesn't specify required headers
3. **No URL Construction** - Azure uses deployment-specific URL format
4. **No Environment Configuration** - Missing config for Azure resource name, deployment ID, API version

---

## Implementation Plan

### Phase 1: Provider Configuration

**File: `providers/azure.py`**

Add configuration constants and helper functions:

```python
# Add to providers/azure.py

# Azure OpenAI configuration
supports_prompt_caching = False  # Azure doesn't expose prompt caching
supports_message_cache_control = False

# Environment variable names
ENV_AZURE_ENDPOINT = "AZURE_OPENAI_ENDPOINT"      # e.g., https://myresource.openai.azure.com
ENV_AZURE_API_KEY = "AZURE_OPENAI_API_KEY"
ENV_AZURE_DEPLOYMENT = "AZURE_OPENAI_DEPLOYMENT"  # e.g., gpt-4o-deployment
ENV_AZURE_API_VERSION = "AZURE_OPENAI_API_VERSION"  # default: 2024-08-01-preview

DEFAULT_API_VERSION = "2024-08-01-preview"

def get_headers() -> dict:
    """Get Azure OpenAI authentication headers."""
    api_key = os.environ.get(ENV_AZURE_API_KEY)
    if not api_key:
        raise ValueError(f"Missing {ENV_AZURE_API_KEY} environment variable")
    return {
        "api-key": api_key,
        "Content-Type": "application/json"
    }

def get_endpoint_url() -> str:
    """Construct Azure OpenAI endpoint URL."""
    base = os.environ.get(ENV_AZURE_ENDPOINT)
    deployment = os.environ.get(ENV_AZURE_DEPLOYMENT)
    api_version = os.environ.get(ENV_AZURE_API_VERSION, DEFAULT_API_VERSION)

    if not base or not deployment:
        raise ValueError(f"Missing {ENV_AZURE_ENDPOINT} or {ENV_AZURE_DEPLOYMENT}")

    return f"{base.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"
```

### Phase 2: Client HTTP Layer Updates

**File: `llm/clients/streaming.py`**

Update `iter_sse_lines()` to accept optional headers:

```python
def iter_sse_lines(
    self,
    url: str,
    *,
    method: str = "POST",
    json_data: Optional[dict] = None,
    params: Optional[Dict[str, str]] = None,
    headers: Optional[Dict[str, str]] = None,  # NEW
    timeout: float = 60.0,
    session: Optional[requests.Session] = None,
) -> Iterator[str]:
    sse_session = session or requests.Session()
    req = sse_session.get if method.upper() == "GET" else sse_session.post

    with req(url, json=json_data, params=params, headers=headers, stream=True, timeout=timeout) as r:
        r.raise_for_status()
        for raw in r.iter_lines(decode_unicode=True):
            if not raw:
                continue
            yield raw[5:].lstrip() if raw.startswith("data:") else raw
```

**File: `llm/clients/blocking.py`**

Update `_make_request()` to accept headers:

```python
def _make_request(
    self, url: str, payload: dict, timeout: Optional[float] = None,
    headers: Optional[dict] = None, **kwargs  # NEW
) -> dict:
    self.spinner.start()
    try:
        timeout_val = timeout or self.timeout
        response = requests.post(url, json=payload, headers=headers, timeout=timeout_val)
        response.raise_for_status()
        return response.json()
    finally:
        self.spinner.stop()
```

### Phase 3: Session Integration

**File: `chat/session.py`**

Update `ChatSession` to handle provider-specific URL and headers:

```python
class ChatSession:
    def __init__(
        self,
        url: str,           # Can be overridden by provider
        provider,
        ...
    ):
        self.base_url = url
        self.provider = provider

    def _get_request_config(self) -> tuple[str, dict]:
        """Get provider-specific URL and headers."""
        # Check if provider has its own endpoint configuration
        if hasattr(self.provider, 'get_endpoint_url'):
            try:
                url = self.provider.get_endpoint_url()
            except ValueError:
                url = self.base_url  # Fall back to CLI-provided URL
        else:
            url = self.base_url

        # Get provider-specific headers
        if hasattr(self.provider, 'get_headers'):
            try:
                headers = self.provider.get_headers()
            except ValueError:
                headers = {}
        else:
            headers = {}

        return url, headers
```

### Phase 4: CLI Integration

**File: `ride_rails.py`**

Add Azure-specific CLI options and environment variable hints:

```python
parser.add_argument(
    "--azure-endpoint",
    help="Azure OpenAI endpoint (or set AZURE_OPENAI_ENDPOINT env var)"
)
parser.add_argument(
    "--azure-deployment",
    help="Azure OpenAI deployment name (or set AZURE_OPENAI_DEPLOYMENT env var)"
)
```

Add startup validation for Azure provider:

```python
if args.provider == "azure":
    # Verify Azure configuration
    missing = []
    if not os.environ.get("AZURE_OPENAI_ENDPOINT") and not args.azure_endpoint:
        missing.append("AZURE_OPENAI_ENDPOINT")
    if not os.environ.get("AZURE_OPENAI_API_KEY"):
        missing.append("AZURE_OPENAI_API_KEY")
    if not os.environ.get("AZURE_OPENAI_DEPLOYMENT") and not args.azure_deployment:
        missing.append("AZURE_OPENAI_DEPLOYMENT")

    if missing:
        console.print(f"[red]Missing Azure config: {', '.join(missing)}[/red]")
        return 1
```

### Phase 5: Testing

**File: `tests/test_azure_provider.py`**

Create comprehensive tests:

```python
import pytest
from providers import azure

class TestAzurePayloadBuild:
    def test_build_payload_basic(self):
        messages = [{"role": "user", "content": "Hello"}]
        payload = azure.build_payload(messages, model="gpt-4o")

        assert payload["stream"] is True
        assert payload["model"] == "gpt-4o"
        assert len(payload["messages"]) >= 2  # system + user

    def test_build_payload_with_tools(self):
        messages = [{"role": "user", "content": "Search for foo"}]
        tools = [{
            "name": "search",
            "description": "Search the codebase",
            "input_schema": {"type": "object", "properties": {}}
        }]
        payload = azure.build_payload(messages, tools=tools)

        assert "tools" in payload
        assert payload["tools"][0]["type"] == "function"

class TestAzureEventMapping:
    def test_map_text_events(self):
        lines = iter([
            '{"model": "gpt-4o", "choices": [{"delta": {"content": "Hello"}}]}',
            '{"choices": [{"delta": {"content": " world"}}]}',
            '{"choices": [{"finish_reason": "stop"}], "usage": {"total_tokens": 10}}'
        ])
        events = list(azure.map_events(lines))

        assert ("model", "gpt-4o") in events
        assert ("text", "Hello") in events
        assert ("text", " world") in events

    def test_map_tool_call_events(self):
        lines = iter([
            '{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "search", "arguments": ""}}]}}]}',
            '{"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": "{\\"q\\": \\"test\\"}"}}]}}]}',
            '{"choices": [{"finish_reason": "tool_calls"}]}'
        ])
        events = list(azure.map_events(lines))

        tool_start_events = [e for e in events if e[0] == "tool_start"]
        assert len(tool_start_events) == 1
```

**File: `tests/test_azure_integration.py`**

Integration test with mocked Azure API:

```python
@pytest.fixture
def mock_azure_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-deploy")

def test_azure_endpoint_construction(mock_azure_env):
    from providers import azure
    url = azure.get_endpoint_url()
    assert "test.openai.azure.com" in url
    assert "gpt-4o-deploy" in url
    assert "api-version=" in url

def test_azure_headers(mock_azure_env):
    from providers import azure
    headers = azure.get_headers()
    assert headers["api-key"] == "test-key"
```

---

## Implementation Order

1. **Phase 1** - Provider configuration (1 file change)
   - Add `get_headers()`, `get_endpoint_url()`, environment constants
   - Add `supports_prompt_caching = False`

2. **Phase 2** - Client HTTP updates (2 files)
   - Update `iter_sse_lines()` with headers parameter
   - Update blocking client `_make_request()` with headers

3. **Phase 3** - Session integration (1 file)
   - Add `_get_request_config()` method
   - Wire headers into request calls

4. **Phase 4** - CLI updates (1 file)
   - Add Azure-specific arguments
   - Add startup validation

5. **Phase 5** - Testing (2 new files)
   - Unit tests for payload/event mapping
   - Integration tests with mocked API

---

## Environment Variables

```bash
# Required for Azure provider
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
export AZURE_OPENAI_API_KEY="your-api-key"
export AZURE_OPENAI_DEPLOYMENT="your-deployment-name"

# Optional
export AZURE_OPENAI_API_VERSION="2024-08-01-preview"  # default
```

---

## Usage Example

```bash
# With environment variables set
python ride_rails.py --project /path/to/rails --provider azure

# Or with CLI overrides (API key still from env)
python ride_rails.py --project /path/to/rails --provider azure \
  --azure-endpoint https://myresource.openai.azure.com \
  --azure-deployment gpt-4o-deployment
```

---

## Alternative: Gateway Approach

If you prefer to keep the client simple and use the existing gateway pattern:

1. Create an Azure gateway server (FastAPI/Flask) that:
   - Receives requests at `http://127.0.0.1:8000/invoke`
   - Adds Azure authentication headers
   - Forwards to Azure OpenAI API
   - Returns response

2. Benefits:
   - No client code changes needed
   - Same architecture as Bedrock gateway
   - Easier credential management (server-side only)

3. Drawback:
   - Requires running additional server process

---

## Notes

- The existing `azure.py` payload building and event mapping is production-ready
- Main gap is HTTP transport layer (authentication, URL construction)
- Azure doesn't support prompt caching exposed via API (internal only)
- GPT models don't stream thinking like Claude - `reasoning_effort` is different
- Cost calculation uses GPT-5 rates - update if using different model
