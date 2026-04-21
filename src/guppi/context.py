"""Conversation history management.

The Anthropic Messages API is stateless — every request resends the full
history. This module owns that list and keeps it under a rough token
budget via two mechanisms:

  * Pair-wise truncation: drop oldest user+assistant pairs when the total
    estimated token count exceeds the configured ceiling. Pair-wise,
    because an orphaned tool_result (without its matching tool_use) is a
    hard API error.
  * Per-tool-result clipping: tool outputs (shell transcripts especially)
    dwarf user prose, so we clip each result at ingestion time.

Nothing here is a precise tokenizer — we use a 4-chars-per-token
heuristic. That over-counts by a small margin, which is the safe side.
"""

from __future__ import annotations

import json
from typing import Any

# Roughly 4 characters per token for English + code. This deliberately
# overestimates so we truncate a little early rather than too late.
_CHARS_PER_TOKEN = 4


def _estimate_tokens(obj: Any) -> int:
    """Return an approximate token count for any JSON-serializable object."""
    if isinstance(obj, str):
        return len(obj) // _CHARS_PER_TOKEN
    return len(json.dumps(obj, default=str)) // _CHARS_PER_TOKEN


def clip_tool_result(content: str, max_tokens: int) -> str:
    """Clip a tool result to ~max_tokens, appending a note when truncated.

    The Anthropic API accepts either a string or a list of content blocks
    for a tool_result. We always produce a string here; the caller wraps
    it in the block structure.
    """
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(content) <= max_chars:
        return content
    kept = content[:max_chars]
    return f"{kept}\n\n[truncated — original output was {len(content)} chars]"


class ConversationHistory:
    """A mutable list of Anthropic message dicts plus token accounting."""

    def __init__(self, max_tokens: int) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_tokens = max_tokens

    @property
    def messages(self) -> list[dict[str, Any]]:
        """The message list, safe to pass directly to `client.messages.create`."""
        return self._messages

    def append(self, message: dict[str, Any]) -> None:
        self._messages.append(message)

    def extend(self, messages: list[dict[str, Any]]) -> None:
        self._messages.extend(messages)

    def clear(self) -> None:
        self._messages.clear()

    def estimated_tokens(self) -> int:
        return sum(_estimate_tokens(m) for m in self._messages)

    def truncate_if_needed(self) -> int:
        """Drop oldest user+assistant pairs until under the token budget.

        Returns the number of messages dropped (0 if no truncation was
        required). The caller is expected to render a warning when the
        return value is non-zero so the user knows we lost context.
        """
        dropped = 0
        # Drop in pairs from the front. Never remove the most recent
        # user message — we always need at least one turn to reason on.
        while (
            self.estimated_tokens() > self._max_tokens
            and len(self._messages) > 2
        ):
            # Remove the oldest two entries (typically user, then assistant).
            del self._messages[0:2]
            dropped += 2
        return dropped
