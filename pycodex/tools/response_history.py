"""Response history helpers ported from ``codex-rs/tools/src/response_history.rs``."""

from __future__ import annotations

from collections.abc import MutableSequence
from typing import Any

from pycodex.protocol import ContentItem, ResponseItem, TruncationPolicyConfig
from pycodex.utils.output_truncation import truncate_text
from pycodex.utils.string import approx_token_count


def retain_tail_from_last_n_user_messages(
    items: MutableSequence[ResponseItem | dict[str, Any]],
    user_message_count: int,
) -> None:
    if user_message_count < 0:
        raise ValueError("user_message_count must be non-negative")
    if user_message_count == 0:
        del items[:]
        return

    latest_user_idx = _latest_user_message_index(items)
    if latest_user_idx is None:
        del items[:]
        return

    del items[latest_user_idx + 1 :]

    retained = 0
    earliest_retained_user_idx = latest_user_idx
    for idx in range(len(items) - 1, -1, -1):
        if _is_user_message(items[idx]):
            retained += 1
            earliest_retained_user_idx = idx
            if retained >= user_message_count:
                break

    del items[:earliest_retained_user_idx]


def truncate_assistant_output_text_to_token_budget(
    items: MutableSequence[ResponseItem | dict[str, Any]],
    max_tokens: int,
) -> None:
    if max_tokens < 0:
        raise ValueError("max_tokens must be non-negative")

    remaining_budget = max_tokens
    retained_items: list[ResponseItem | dict[str, Any]] = []

    for item in items:
        if not _is_assistant_message(item):
            retained_items.append(item)
            continue

        content = _message_content(item)
        retained_content: list[ContentItem | dict[str, Any]] = []
        changed = False
        for content_item in content:
            if not _is_output_text(content_item):
                retained_content.append(content_item)
                continue
            if remaining_budget == 0:
                changed = True
                continue

            text = _content_text(content_item)
            token_count = approx_token_count(text)
            if token_count <= remaining_budget:
                remaining_budget -= token_count
                retained_content.append(content_item)
                continue

            truncated_text = truncate_text(text, TruncationPolicyConfig.tokens(remaining_budget))
            retained_content.append(_with_content_text(content_item, truncated_text))
            remaining_budget = 0
            changed = True

        if retained_content:
            retained_items.append(_with_message_content(item, retained_content) if changed else item)

    items[:] = retained_items


def _latest_user_message_index(items: MutableSequence[ResponseItem | dict[str, Any]]) -> int | None:
    for idx in range(len(items) - 1, -1, -1):
        if _is_user_message(items[idx]):
            return idx
    return None


def _is_user_message(item: ResponseItem | dict[str, Any]) -> bool:
    return _item_type(item) == "message" and _item_role(item) == "user"


def _is_assistant_message(item: ResponseItem | dict[str, Any]) -> bool:
    return _item_type(item) == "message" and _item_role(item) == "assistant"


def _item_type(item: ResponseItem | dict[str, Any]) -> str | None:
    return item.type if isinstance(item, ResponseItem) else item.get("type")


def _item_role(item: ResponseItem | dict[str, Any]) -> str | None:
    return item.role if isinstance(item, ResponseItem) else item.get("role")


def _message_content(item: ResponseItem | dict[str, Any]) -> tuple[ContentItem | dict[str, Any], ...]:
    raw_content = item.content if isinstance(item, ResponseItem) else item.get("content", ())
    return tuple(raw_content or ())


def _is_output_text(content_item: ContentItem | dict[str, Any]) -> bool:
    content_type = content_item.type if isinstance(content_item, ContentItem) else content_item.get("type")
    return content_type == "output_text"


def _content_text(content_item: ContentItem | dict[str, Any]) -> str:
    text = content_item.text if isinstance(content_item, ContentItem) else content_item.get("text")
    if not isinstance(text, str):
        raise TypeError("output_text content item text must be a string")
    return text


def _with_content_text(content_item: ContentItem | dict[str, Any], text: str) -> ContentItem | dict[str, Any]:
    if isinstance(content_item, ContentItem):
        return ContentItem.output_text(text)
    updated = dict(content_item)
    updated["text"] = text
    return updated


def _with_message_content(
    item: ResponseItem | dict[str, Any],
    content: list[ContentItem | dict[str, Any]],
) -> ResponseItem | dict[str, Any]:
    if isinstance(item, ResponseItem):
        return ResponseItem.message(
            item.role or "",
            tuple(_coerce_content_item(content_item) for content_item in content),
            id=item.id,
            phase=item.phase,
        )
    updated = dict(item)
    updated["content"] = list(content)
    return updated


def _coerce_content_item(content_item: ContentItem | dict[str, Any]) -> ContentItem:
    return content_item if isinstance(content_item, ContentItem) else ContentItem.from_mapping(content_item)


__all__ = [
    "retain_tail_from_last_n_user_messages",
    "truncate_assistant_output_text_to_token_budget",
]
