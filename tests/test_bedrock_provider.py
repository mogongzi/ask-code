import copy
from types import SimpleNamespace

from agent.llm_client import LLMClient
from providers import bedrock
from prompts.system_prompt import RAILS_REACT_SYSTEM_PROMPT


def test_supports_prompt_caching_enabled():
    assert bedrock.supports_prompt_caching is True


def test_build_payload_formats_system_prompt_with_cache_blocks():
    """Test that system prompt is formatted with cache_control on LAST block only.

    The new caching strategy only marks the last system block to optimize
    breakpoint usage (only 1 breakpoint for entire static prefix).
    """
    payload = bedrock.build_payload(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt=RAILS_REACT_SYSTEM_PROMPT,
    )

    assert "system" in payload
    system_blocks = payload["system"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 1

    # Only the LAST block should have cache_control
    last_block = system_blocks[-1]
    assert last_block["cache_control"]["type"] == "ephemeral"

    # Other blocks (if any) should NOT have cache_control
    for block in system_blocks[:-1]:
        assert "cache_control" not in block

    # First block should contain the agent instructions
    first_block = system_blocks[0]
    assert "You are" in first_block["text"] or "Rails" in first_block["text"]


def test_build_payload_preserves_existing_block_metadata():
    system_blocks = [{"type": "text", "text": "cached text"}]
    original_blocks = copy.deepcopy(system_blocks)

    payload = bedrock.build_payload(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt=system_blocks,
    )

    assert system_blocks == original_blocks  # input not mutated
    assert "cache_control" not in system_blocks[0]

    formatted_blocks = payload["system"]
    assert formatted_blocks[0]["cache_control"]["type"] == "ephemeral"


def test_llm_client_applies_cache_control_for_bedrock(monkeypatch):
    """Test that LLMClient DOES add cache_control to last two user messages for Bedrock.

    With supports_message_cache_control = True, the Cline-style caching
    strategy marks the last two user messages with cache_control.
    """
    captured_payload = {}
    original_build_payload = bedrock.build_payload

    def wrapped_build_payload(*args, **kwargs):
        payload = original_build_payload(*args, **kwargs)
        captured_payload["messages"] = payload["messages"]
        return payload

    monkeypatch.setattr(bedrock, "build_payload", wrapped_build_payload)

    class DummyStreamingClient:
        def __init__(self):
            self.sent_payload = None

        def send_message(self, url, payload, mapper, provider_name):
            self.sent_payload = payload
            return SimpleNamespace(text="", tool_calls=[], tokens=0, cost=0.0, error=None)

    session = SimpleNamespace(
        provider=bedrock,
        streaming_client=DummyStreamingClient(),
        url="http://test",
        provider_name="bedrock",
        max_tokens=2048,
        usage_tracker=None,
    )

    client = LLMClient(session=session)

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "initial query"},
        {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": "tool-1",
                    "name": "test_tool",
                    "input": {"arg": "value"},
                }
            ],
        },
        {"role": "user", "content": "follow-up"},
    ]

    client.call_llm(messages, tool_schemas=[])

    assert captured_payload["messages"], "Payload messages should be captured"

    # Helper to check if a message has cache_control
    def has_cache_control(msg):
        content = msg.get("content")
        if isinstance(content, list):
            return any(
                isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
                for b in content
            )
        return False

    # After stripping system, messages are:
    # [0] user "initial query" - should have cache_control (2nd-to-last user)
    # [1] assistant with tool_use - should NOT have cache_control
    # [2] user "follow-up" - should have cache_control (last user)
    first_user = captured_payload["messages"][0]
    assistant_msg = captured_payload["messages"][1]
    last_user = captured_payload["messages"][2]

    # Last two USER messages should have cache_control
    assert has_cache_control(first_user), "First user message should have cache_control"
    assert has_cache_control(last_user), "Last user message should have cache_control"

    # Assistant message should NOT have cache_control on tool_use blocks
    assert "cache_control" not in assistant_msg
    tool_block = assistant_msg["content"][0]
    assert "cache_control" not in tool_block


def test_build_payload_places_tools_before_messages():
    payload = bedrock.build_payload(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt=RAILS_REACT_SYSTEM_PROMPT,
        tools=[{"name": "dummy", "description": "test", "input_schema": {"type": "object"}}],
    )

    keys = list(payload.keys())
    assert "tools" in payload
    assert keys.index("tools") < keys.index("messages")
    assert "system" in payload
    assert keys.index("system") < keys.index("tools")
