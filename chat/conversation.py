"""Conversation history management."""

from typing import Any, Dict, List


class ConversationManager:
    """Manages conversation history, compression, and sanitization."""

    def __init__(self, max_history_tokens: int = 10000, recent_tool_results: int = 2):
        self.history: List[dict] = []
        self.max_history_tokens = max_history_tokens
        self.recent_tool_results = max(0, recent_tool_results)
        self._summary_max_chars = 160

    def add_user_message(self, content: str) -> None:
        """Add a user message to conversation history."""
        self.history.append({"role": "user", "content": content})

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to conversation history."""
        if content and content.strip():  # Only add non-empty responses
            self.history.append({"role": "assistant", "content": content})

    def add_tool_messages(self, tool_messages: List[dict]) -> None:
        """Add tool call and result messages to conversation history."""
        self.history.extend(tool_messages)
        self._compress_history_if_needed()

    def append_to_last_user_message(self, text: str) -> None:
        """Append text to the most recent user message, creating one if needed."""
        if not text:
            return

        if not self.history or self.history[-1].get("role") != "user":
            self.history.append({"role": "user", "content": text})
            return

        last_message = self.history[-1]
        content = last_message.get("content")

        if isinstance(content, list):
            content.append({"type": "text", "text": text})
        elif isinstance(content, str):
            last_message["content"] = f"{content}\n{text}" if content else text
        else:
            last_message["content"] = text

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self.history = []

    def get_sanitized_history(self) -> List[dict]:
        """Get conversation history with empty assistant messages filtered out."""
        cleaned_history = []
        for msg in self.history:
            if msg["role"] == "assistant":
                # Skip empty assistant responses that break conversation flow
                content = msg["content"]
                if isinstance(content, str) and not content.strip():
                    continue  # Skip empty string content
                elif isinstance(content, list) and not content:
                    continue  # Skip empty tool use blocks
            cleaned_history.append(msg)
        return cleaned_history

    def get_user_history(self) -> List[str]:
        """Extract user message contents for input navigation."""
        return [
            msg["content"]
            for msg in self.history
            if msg["role"] == "user" and isinstance(msg["content"], str)
        ]

    # Internal helpers -------------------------------------------------

    def _compress_history_if_needed(self) -> None:
        """Compress and trim history when estimated tokens exceed budget."""
        if not self.max_history_tokens or self.max_history_tokens <= 0:
            return

        # Fast path: under budget
        if self._estimate_tokens(self.history) <= self.max_history_tokens:
            return

        # Step 1: compress older tool results
        self._compress_tool_results()

    def _compress_tool_results(self) -> None:
        """Replace older tool results with concise summaries."""
        tool_result_indices = [
            idx for idx, message in enumerate(self.history)
            if self._is_tool_result_message(message)
        ]

        if not tool_result_indices:
            return

        keep_indices = set(tool_result_indices[-self.recent_tool_results:]) if self.recent_tool_results else set()

        tool_lookup = self._build_tool_lookup()

        for idx in tool_result_indices:
            if idx in keep_indices:
                continue

            message = self.history[idx]
            content = message.get("content")
            if isinstance(content, str):  # Already compressed
                continue

            summary = self._summarize_tool_result(content or [], tool_lookup)
            metadata = dict(message.get("metadata") or {})
            metadata["compressed"] = True

            self.history[idx] = {
                "role": "user",
                "content": summary,
                "metadata": metadata,
            }

    def _build_tool_lookup(self) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for message in self.history:
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_id = block.get("id")
                    tool_name = block.get("name")
                    if tool_id and tool_name:
                        lookup[tool_id] = tool_name
        return lookup

    def _summarize_tool_result(self, content: List[Any], tool_lookup: Dict[str, str]) -> str:
        parts: List[str] = []

        for block in content:
            if isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "tool_result":
                    tool_id = block.get("tool_use_id")
                    tool_name = tool_lookup.get(tool_id, "Result")
                    snippet = self._trim_text(block.get("content", ""))
                    if snippet:
                        parts.append(f"{tool_name}: {snippet}")
                elif block_type == "text":
                    note = self._trim_text(block.get("text", ""))
                    if note:
                        parts.append(f"Context: {note}")
            elif isinstance(block, str):
                snippet = self._trim_text(block)
                if snippet:
                    parts.append(snippet)

        if not parts:
            return "[compressed tool results]"

        return "Earlier results → " + " | ".join(parts)

    def _is_tool_result_message(self, message: Dict[str, Any]) -> bool:
        if message.get("role") != "user":
            return False
        content = message.get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(block, dict) and block.get("type") == "tool_result"
            for block in content
        )

    def _estimate_tokens(self, messages: List[Dict[str, Any]]) -> int:
        total_chars = 0
        for message in messages:
            content = message.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        block_type = block.get("type")
                        if block_type == "tool_use":
                            total_chars += len(block.get("name", ""))
                            total_chars += len(str(block.get("input", "")))
                        elif block_type == "tool_result":
                            total_chars += len(str(block.get("content", "")))
                        elif block_type == "text":
                            total_chars += len(block.get("text", ""))
                        else:
                            total_chars += len(str(block))
                    else:
                        total_chars += len(str(block))
            elif isinstance(content, str):
                total_chars += len(content)
            elif content is not None:
                total_chars += len(str(content))

        return total_chars // 4

    def _trim_text(self, value: Any) -> str:
        if value is None:
            return ""
        text = " ".join(str(value).split())
        if not text:
            return ""
        if len(text) > self._summary_max_chars:
            return text[: self._summary_max_chars].rstrip() + "..."
        return text
