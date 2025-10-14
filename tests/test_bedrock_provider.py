import copy
from types import SimpleNamespace

from agent.llm_client import LLMClient
from providers import bedrock
from prompts.system_prompt import RAILS_REACT_SYSTEM_PROMPT


def test_supports_prompt_caching_enabled():
    assert bedrock.supports_prompt_caching is True


def test_build_payload_formats_system_prompt_with_cache_blocks():
    payload = bedrock.build_payload(
        messages=[{"role": "user", "content": "Hello"}],
        system_prompt=RAILS_REACT_SYSTEM_PROMPT,
    )

    assert "system" in payload
    system_blocks = payload["system"]
    assert isinstance(system_blocks, list)
    assert len(system_blocks) >= 2

    first_block = system_blocks[0]
    second_block = system_blocks[1]

    assert first_block["cache_control"]["type"] == "ephemeral"
    assert "You are an expert Rails Code Detective" in first_block["text"]
    assert second_block["cache_control"]["type"] == "ephemeral"
    assert second_block["text"].startswith("# Tool Usage (ReAct Pattern)")


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


def test_llm_client_does_not_add_cache_control_for_bedrock(monkeypatch):
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
    for message in captured_payload["messages"]:
        assert "cache_control" not in message

    assistant_message = captured_payload["messages"][1]  # first user removed system prompt
    tool_block = assistant_message["content"][0]
    assert "cache_control" not in tool_block
