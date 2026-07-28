"""Conversation-tail selection from Rust ``web-search/src/history.rs``."""

from __future__ import annotations

from collections.abc import Sequence

from pycodex.codex_api import SearchInput
from pycodex.core.event_mapping import parse_turn_item
from pycodex.protocol import ResponseItem
from pycodex.tools import (
    retain_tail_from_last_n_user_messages,
    truncate_assistant_output_text_to_token_budget,
)

ASSISTANT_CONTEXT_TOKEN_LIMIT = 1_000


def recent_input(items: Sequence[ResponseItem]) -> SearchInput | None:
    messages: list[ResponseItem] = []
    for item in items:
        _push_visible_message(messages, item)
    retain_tail_from_last_n_user_messages(messages, 2)
    truncate_assistant_output_text_to_token_budget(
        messages,
        ASSISTANT_CONTEXT_TOKEN_LIMIT,
    )
    return SearchInput.items(messages) if messages else None


def _push_visible_message(
    messages: list[ResponseItem],
    item: ResponseItem,
) -> None:
    if item.type != "message":
        return
    if item.role == "assistant":
        messages.append(item)
        return
    if item.role != "user" or parse_turn_item(item) is None:
        return
    content = tuple(part for part in item.content if part.type == "input_text")
    if content:
        messages.append(
            ResponseItem.message(
                role="user",
                content=content,
                id=item.id,
                phase=item.phase,
            )
        )


__all__ = ["recent_input"]
