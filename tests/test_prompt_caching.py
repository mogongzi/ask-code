"""Tests for prompt caching implementation.

Tests the Cline-style "last two user messages" caching strategy.
"""

import pytest
from providers import bedrock
from llm.types import UsageInfo
from llm.parsers.bedrock import BedrockResponseParser


class TestBedrockCacheSupport:
    """Tests for Bedrock provider cache support flags."""

    def test_supports_prompt_caching_enabled(self):
        """Bedrock should support prompt caching."""
        assert bedrock.supports_prompt_caching is True

    def test_supports_message_cache_control_enabled(self):
        """Bedrock should support message-level cache control."""
        assert bedrock.supports_message_cache_control is True


class TestUsageInfoCacheFields:
    """Tests for UsageInfo cache fields."""

    def test_has_cache_fields(self):
        """UsageInfo should have cache creation and read fields."""
        usage = UsageInfo(
            input_tokens=893,
            output_tokens=338,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=1278
        )
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 1278

    def test_default_cache_fields_are_zero(self):
        """Cache fields should default to zero."""
        usage = UsageInfo()
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 0


class TestBedrockParserCacheExtraction:
    """Tests for BedrockResponseParser cache metric extraction."""

    def test_extract_cache_metrics_from_actual_response(self):
        """Test with actual Bedrock response format."""
        parser = BedrockResponseParser()
        response = {
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {
                "cache_creation": {
                    "ephemeral_1h_input_tokens": 0,
                    "ephemeral_5m_input_tokens": 0
                },
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 1278,
                "input_tokens": 893,
                "output_tokens": 338
            }
        }
        usage = parser.extract_usage(response)
        assert usage.input_tokens == 893
        assert usage.output_tokens == 338
        assert usage.cache_creation_input_tokens == 0
        assert usage.cache_read_input_tokens == 1278

    def test_extract_cache_metrics_with_cache_creation(self):
        """Test extraction when cache is being written."""
        parser = BedrockResponseParser()
        response = {
            "content": [{"type": "text", "text": "Hello"}],
            "usage": {
                "cache_creation_input_tokens": 5000,
                "cache_read_input_tokens": 0,
                "input_tokens": 100,
                "output_tokens": 200
            }
        }
        usage = parser.extract_usage(response)
        assert usage.cache_creation_input_tokens == 5000
        assert usage.cache_read_input_tokens == 0

    def test_total_tokens_includes_cache_read(self):
        """Total tokens should include cache read for context tracking."""
        parser = BedrockResponseParser()
        response = {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 200,
                "cache_read_input_tokens": 1000
            }
        }
        usage = parser.extract_usage(response)
        # total = input + output + cache_read
        assert usage.total_tokens == 100 + 200 + 1000


class TestCacheAwareCostCalculation:
    """Tests for cache-aware cost calculation."""

    def test_cache_read_reduces_cost(self):
        """Reading from cache should be cheaper than regular input."""
        parser = BedrockResponseParser()

        # With cache read (1278 tokens cached at 0.1x rate)
        cached = parser._calculate_cost_with_cache(893, 338, 0, 1278)

        # Without cache (all as regular input at full rate)
        uncached = parser._calculate_cost_with_cache(893 + 1278, 338, 0, 0)

        assert cached < uncached

    def test_cache_write_costs_more(self):
        """Writing to cache should cost more (1.25x input rate)."""
        parser = BedrockResponseParser()

        # With cache write
        with_write = parser._calculate_cost_with_cache(100, 100, 1000, 0)

        # Without cache write
        without_write = parser._calculate_cost_with_cache(100, 100, 0, 0)

        assert with_write > without_write

    def test_cost_calculation_rates(self):
        """Verify specific cost calculation rates."""
        parser = BedrockResponseParser()

        # 1000 input tokens at $0.003/1K = $0.003
        # 1000 output tokens at $0.015/1K = $0.015
        # 1000 cache write tokens at $0.00375/1K = $0.00375
        # 1000 cache read tokens at $0.0003/1K = $0.0003
        cost = parser._calculate_cost_with_cache(1000, 1000, 1000, 1000)
        expected = 0.003 + 0.015 + 0.00375 + 0.0003
        assert abs(cost - expected) < 0.0001


class TestPromptCachingApplication:
    """Tests for prompt caching application to messages."""

    def test_marks_last_two_user_messages(self):
        """Should mark the last two user messages with cache_control."""
        from agent.llm_client import LLMClient

        client = LLMClient(session=None)
        messages = [
            {"role": "user", "content": "First"},
            {"role": "assistant", "content": "Reply 1"},
            {"role": "user", "content": "Second"},
            {"role": "assistant", "content": "Reply 2"},
            {"role": "user", "content": "Third"},
        ]

        client._apply_prompt_caching(messages)

        # Helper to check cache_control safely
        def has_cache_control(msg):
            content = msg.get("content")
            if isinstance(content, str):
                return False
            if isinstance(content, list):
                return any(
                    isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
                    for b in content
                )
            return False

        # Last two user messages (indices 2 and 4) should have cache_control
        assert has_cache_control(messages[2])
        assert has_cache_control(messages[4])
        # First user message should NOT have cache_control
        assert not has_cache_control(messages[0])

    def test_turn_1_marks_single_message(self):
        """Turn 1 should mark the single user message for cache write."""
        from agent.llm_client import LLMClient

        client = LLMClient(session=None)
        messages = [
            {"role": "user", "content": "First query"},
        ]

        client._apply_prompt_caching(messages)

        # Helper to check cache_control
        def has_cache_control(msg):
            content = msg.get("content")
            if isinstance(content, str):
                return False
            if isinstance(content, list):
                return any(
                    isinstance(b, dict) and b.get("cache_control") == {"type": "ephemeral"}
                    for b in content
                )
            return False

        # Single user message should be marked for caching
        assert has_cache_control(messages[0])

    def test_tool_result_message_gets_text_block(self):
        """Tool_result-only messages should get a placeholder text block for caching."""
        from agent.llm_client import LLMClient

        client = LLMClient(session=None)
        messages = [
            {"role": "user", "content": "First query"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "test", "input": {}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "result"}]},
        ]

        client._apply_prompt_caching(messages)

        # The tool_result message should now have a text block added
        tool_result_msg = messages[2]
        content = tool_result_msg.get("content", [])
        assert isinstance(content, list)

        # Should have both tool_result and text blocks
        types = [b.get("type") for b in content if isinstance(b, dict)]
        assert "tool_result" in types
        assert "text" in types

        # The text block should have "." as placeholder (not empty - API rejects empty)
        text_block = next(b for b in content if isinstance(b, dict) and b.get("type") == "text")
        assert text_block.get("text") == "."

    def test_ensure_cacheable_returns_true_for_string(self):
        """String content should be cacheable."""
        from agent.llm_client import LLMClient

        client = LLMClient(session=None)
        msg = {"role": "user", "content": "Hello"}

        result = client._ensure_cacheable_text_block(msg)
        assert result is True

    def test_ensure_cacheable_returns_false_for_empty_string(self):
        """Empty string content should not be cacheable."""
        from agent.llm_client import LLMClient

        client = LLMClient(session=None)
        msg = {"role": "user", "content": "   "}

        result = client._ensure_cacheable_text_block(msg)
        assert result is False


class TestSystemPromptCaching:
    """Tests for system prompt cache breakpoint placement."""

    def test_system_prompt_has_cache_on_last_block_only(self):
        """Only the last system block should have cache_control."""
        system_prompt = """You are a helpful assistant.

# Tool Usage (ReAct Pattern)
Use tools as needed."""

        result = bedrock._format_system_prompt(system_prompt)

        assert result is not None
        assert len(result) == 2

        # First block should NOT have cache_control
        assert "cache_control" not in result[0]

        # Last block should have cache_control
        assert result[-1].get("cache_control") == {"type": "ephemeral"}

    def test_tools_only_cached_when_no_system(self):
        """Tools should only get cache_control when no system prompt exists."""
        # With system prompt - tools should NOT get cache
        tools = [{"name": "tool1"}, {"name": "tool2"}]
        payload = bedrock.build_payload(
            messages=[{"role": "user", "content": "test"}],
            tools=tools.copy(),
            system_prompt="You are helpful."
        )

        # Tools should NOT have cache_control (system has it)
        assert "cache_control" not in payload["tools"][-1]

    def test_tools_cached_when_no_system(self):
        """Tools should get cache_control when no system prompt."""
        tools = [{"name": "tool1"}, {"name": "tool2"}]
        payload = bedrock.build_payload(
            messages=[{"role": "user", "content": "test"}],
            tools=tools.copy(),
            system_prompt=None
        )

        # Last tool should have cache_control
        assert payload["tools"][-1].get("cache_control") == {"type": "ephemeral"}


class TestUsageTrackerCache:
    """Tests for UsageTracker cache tracking."""

    def test_update_with_cache_metrics(self):
        """UsageTracker should track cache metrics."""
        from chat.usage_tracker import UsageTracker

        tracker = UsageTracker()
        tracker.update(1000, 0.01, cache_creation=500, cache_read=300)

        assert tracker.cache_creation_tokens == 500
        assert tracker.cache_read_tokens == 300

    def test_display_includes_cache_indicator(self):
        """Display string should include cache hit indicator."""
        from chat.usage_tracker import UsageTracker

        tracker = UsageTracker()
        tracker.update(1000, 0.01, cache_creation=100, cache_read=900)

        display = tracker.get_display_string()
        assert display is not None
        assert "cache" in display
        assert "90%" in display  # 900 / (900 + 100) = 90%

    def test_cache_summary(self):
        """Cache summary should show detailed breakdown."""
        from chat.usage_tracker import UsageTracker

        tracker = UsageTracker()
        tracker.update(1000, 0.01, cache_creation=1000, cache_read=5000)

        summary = tracker.get_cache_summary()
        assert summary is not None
        assert "written" in summary
        assert "read" in summary
        assert "saved" in summary

    def test_reset_clears_cache_metrics(self):
        """Reset should clear cache metrics."""
        from chat.usage_tracker import UsageTracker

        tracker = UsageTracker()
        tracker.update(1000, 0.01, cache_creation=500, cache_read=300)
        tracker.reset()

        assert tracker.cache_creation_tokens == 0
        assert tracker.cache_read_tokens == 0
