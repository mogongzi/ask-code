"""Conversation history management."""

from typing import List


class ConversationManager:
    """Manages conversation history and message sanitization."""

    def __init__(self):
        self.history: List[dict] = []

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