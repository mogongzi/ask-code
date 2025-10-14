from providers import azure


def test_build_payload_places_tools_before_messages():
    payload = azure.build_payload(
        messages=[{"role": "user", "content": "Hello"}],
        tools=[{"name": "dummy", "description": "test", "input_schema": {"type": "object"}}],
    )

    keys = list(payload.keys())
    assert "tools" in payload
    assert keys.index("tools") < keys.index("messages")

    messages = payload["messages"]
    assert messages
    assert messages[0]["role"] == "system"
